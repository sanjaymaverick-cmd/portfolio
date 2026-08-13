from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from meridian.config import get_settings
from meridian.storage.schema import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        settings.ensure_dirs()
        _engine = create_engine(
            f"sqlite:///{settings.db_path}",
            future=True,
            echo=False,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
    return _engine


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate(engine)


def _migrate(engine: Engine) -> None:
    cols = {column["name"] for column in inspect(engine).get_columns("holdings")}
    statements: list[str] = []
    if "prev_close" not in cols:
        statements.append("ALTER TABLE holdings ADD COLUMN prev_close NUMERIC(20, 4)")
    if "price_asof" not in cols:
        statements.append("ALTER TABLE holdings ADD COLUMN price_asof DATETIME")
    factor_cols = {column["name"] for column in inspect(engine).get_columns("factor_scores")} if "factor_scores" in inspect(engine).get_table_names() else set()
    if factor_cols and "technical_detail" not in factor_cols:
        statements.append("ALTER TABLE factor_scores ADD COLUMN technical_detail TEXT")
    if factor_cols and "ownership_detail" not in factor_cols:
        statements.append("ALTER TABLE factor_scores ADD COLUMN ownership_detail TEXT")
    if factor_cols and "sentiment_detail" not in factor_cols:
        statements.append("ALTER TABLE factor_scores ADD COLUMN sentiment_detail TEXT")
    if factor_cols and "action" not in factor_cols:
        statements.append("ALTER TABLE factor_scores ADD COLUMN action VARCHAR(24)")
    if factor_cols and "confidence" not in factor_cols:
        statements.append("ALTER TABLE factor_scores ADD COLUMN confidence NUMERIC(6, 2)")
    fund_tables = inspect(engine).get_table_names()
    if "fundamentals" in fund_tables:
        fund_cols = {column["name"] for column in inspect(engine).get_columns("fundamentals")}
        for name, ddl in (
            ("promoter_pct", "NUMERIC(10, 4)"),
            ("promoter_pledge", "NUMERIC(10, 4)"),
            ("fii_pct", "NUMERIC(10, 4)"),
            ("dii_pct", "NUMERIC(10, 4)"),
            ("fii_delta", "NUMERIC(10, 4)"),
            ("dii_delta", "NUMERIC(10, 4)"),
            ("analysis_notes", "TEXT"),
        ):
            if name not in fund_cols:
                statements.append(f"ALTER TABLE fundamentals ADD COLUMN {name} {ddl}")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_session() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def session_scope() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
