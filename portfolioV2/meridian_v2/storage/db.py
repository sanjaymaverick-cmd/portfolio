from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from meridian_v2.config import get_settings
from meridian_v2.storage.schema import Base

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
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        _SessionLocal = sessionmaker(
            bind=_engine, autoflush=False, expire_on_commit=False, future=True
        )
    return _engine


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate(engine)


def _migrate(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []
    if "watch_items" in tables:
        cols = {c["name"] for c in inspector.get_columns("watch_items")}
        if "stance" not in cols:
            statements.append("ALTER TABLE watch_items ADD COLUMN stance VARCHAR(16) DEFAULT ''")
        if "sector" not in cols:
            statements.append("ALTER TABLE watch_items ADD COLUMN sector VARCHAR(32) DEFAULT ''")
    if "price_cache" in tables:
        cols = {c["name"] for c in inspector.get_columns("price_cache")}
        for name in (
            "sma20",
            "sma50",
            "weekly_last",
            "weekly_sma",
            "high20",
            "low20",
            "volume",
            "prev_volume",
        ):
            if name not in cols:
                statements.append(f"ALTER TABLE price_cache ADD COLUMN {name} FLOAT")
    if "intended_trades" in tables:
        cols = {c["name"] for c in inspector.get_columns("intended_trades")}
        if "desk_snapshot_json" not in cols:
            statements.append("ALTER TABLE intended_trades ADD COLUMN desk_snapshot_json TEXT DEFAULT '{}'")
        if "outcome_snapshot_json" not in cols:
            statements.append("ALTER TABLE intended_trades ADD COLUMN outcome_snapshot_json TEXT DEFAULT '{}'")
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


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
