from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from meridian.data_providers.service import PriceService
from meridian.data_providers.types import OhlcvBar
from meridian.domain.models import MappedRow
from meridian.storage.repositories import AccountRepo, HoldingRepo
from meridian.storage.schema import Base
from meridian.ui.charts import sparkline


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.series: dict[str, list[OhlcvBar]] = {
            "RELIANCE.NS": _bars(1000, 1010),
            "FAKE.BO": _bars(50, 55),
            "^NSEI": _bars(24000, 24120),
            "^INDIAVIX": _bars(13.2, 12.8),
        }

    def history(self, tickers, period: str = "1y"):  # noqa: ANN001
        self.calls.append(list(tickers))
        return {ticker: self.series[ticker] for ticker in tickers if ticker in self.series}


def _bars(prev: float, last: float) -> list[OhlcvBar]:
    start = date(2026, 8, 1)
    return [
        OhlcvBar(start, Decimal(str(prev)), Decimal(str(prev)), Decimal(str(prev)), Decimal(str(prev))),
        OhlcvBar(
            start + timedelta(days=3),
            Decimal(str(last)),
            Decimal(str(last)),
            Decimal(str(last)),
            Decimal(str(last)),
            Decimal("1000"),
        ),
    ]


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'tape.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_mark_to_market_and_day_pnl(tmp_path: Path) -> None:
    session = _session(tmp_path)
    account = AccountRepo(session).create("Core", "zerodha")
    HoldingRepo(session).upsert(
        account,
        MappedRow(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=Decimal("10"),
            avg_cost=Decimal("900"),
            last_price=Decimal("950"),
        ),
    )
    session.commit()
    fake = FakeProvider()
    result = PriceService(session, provider=fake).refresh(force=True, history=True)
    session.commit()
    assert result.marked == 1
    holding = HoldingRepo(session).list()[0]
    view = HoldingRepo(session).to_view(holding)
    assert view.last_price == Decimal("1010")
    assert view.prev_close == Decimal("1000")
    assert view.day_pnl == Decimal("100")
    assert view.yahoo == "RELIANCE.NS"
    book = HoldingRepo(session).summary([holding])
    assert book.day_pnl == Decimal("100")
    assert book.day_undefined is False


def test_exchange_fallback(tmp_path: Path) -> None:
    session = _session(tmp_path)
    account = AccountRepo(session).create("Core", "zerodha")
    HoldingRepo(session).upsert(
        account,
        MappedRow(symbol="FAKE", exchange="NSE", quantity=Decimal("2"), avg_cost=Decimal("40")),
    )
    session.commit()
    result = PriceService(session, provider=FakeProvider()).refresh(force=True)
    session.commit()
    holding = HoldingRepo(session).list()[0]
    assert holding.yahoo == "FAKE.BO"
    assert holding.last_price == Decimal("55")
    assert result.failed == []


def test_ttl_skips_second_refresh(tmp_path: Path) -> None:
    session = _session(tmp_path)
    account = AccountRepo(session).create("Core", "zerodha")
    HoldingRepo(session).upsert(
        account,
        MappedRow(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=Decimal("1"),
            avg_cost=Decimal("1000"),
        ),
    )
    session.commit()
    fake = FakeProvider()
    service = PriceService(session, provider=fake)
    first = service.refresh(force=True)
    second = service.refresh(force=False)
    assert first.marked == 1
    assert second.skipped == 1
    assert second.marked == 0


def test_fresh_cache_applied_to_new_lot(tmp_path: Path) -> None:
    session = _session(tmp_path)
    accounts = AccountRepo(session)
    holdings = HoldingRepo(session)
    account = accounts.create("Core", "zerodha")
    holdings.upsert(
        account,
        MappedRow(symbol="RELIANCE", exchange="NSE", quantity=Decimal("1"), avg_cost=Decimal("1000")),
    )
    session.commit()
    fake = FakeProvider()
    PriceService(session, provider=fake).refresh(force=True)
    session.commit()
    for row in holdings.list():
        session.delete(row)
    session.flush()
    holdings.upsert(
        account,
        MappedRow(symbol="RELIANCE", exchange="NSE", quantity=Decimal("5"), avg_cost=Decimal("900")),
    )
    session.commit()
    again = PriceService(session, provider=fake).refresh(force=False)
    session.commit()
    holding = holdings.list()[0]
    assert again.marked == 1
    assert holding.last_price == Decimal("1010")
    assert holding.price_asof is not None


def test_sparkline_direction() -> None:
    up = sparkline([1, 2, 3, 4])
    down = sparkline([4, 3, 2, 1])
    assert "#4A9B7F" in up
    assert "#C46B6B" in down
    assert sparkline([1]) == ""
