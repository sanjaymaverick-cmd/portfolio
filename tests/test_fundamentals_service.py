from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from meridian.data_providers.screener import FundamentalSnap
from meridian.domain.models import MappedRow
from meridian.scoring.service import FundamentalService
from meridian.storage.repositories import AccountRepo, HoldingRepo
from meridian.storage.schema import Base


class FakeScreener:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, symbol: str) -> FundamentalSnap:
        self.calls += 1
        return FundamentalSnap(
            symbol=symbol,
            source="screener",
            pe=Decimal("20"),
            pb=Decimal("3"),
            roe=Decimal("15"),
            roce=Decimal("14"),
            opm=Decimal("18"),
            debt_to_equity=Decimal("0.4"),
            cfo_to_op=Decimal("1.0"),
            sector="Energy",
            as_of=datetime.now(),
        )


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'f.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_ttl_and_persist(tmp_path: Path) -> None:
    session = _session(tmp_path)
    account = AccountRepo(session).create("Core", "zerodha")
    HoldingRepo(session).upsert(
        account,
        MappedRow(symbol="RELIANCE", exchange="NSE", quantity=Decimal("1"), avg_cost=Decimal("1000")),
    )
    session.commit()
    fake = FakeScreener()
    service = FundamentalService(session, provider=fake, fallback=None)
    first = service.refresh(force=True)
    second = service.refresh(force=False)
    assert first.marked == 1
    assert second.skipped == 1
    assert fake.calls == 1
    factor = service.factors.get("RELIANCE")
    assert factor is not None and factor.quality is not None and factor.valuation is not None
