from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from meridian.domain.models import MappedRow
from meridian.recommendations.alert_service import AlertService
from meridian.recommendations.alerts import (
    action_hit,
    pledge_hit,
    regime_hit,
    results_hit,
    volume_hit,
    weight_hit,
)
from meridian.storage.alerts import AlertRepo, WatchRepo
from meridian.storage.repositories import AccountRepo, HoldingRepo
from meridian.storage.schema import (
    Attribution,
    Base,
    DailyNews,
    Fundamental,
    RegimeSnapshot,
    RiskSnapshot,
)


def test_weight_and_pledge_and_volume_rules() -> None:
    assert weight_hit("TCS", 10.0, threshold=12, high=15) is None
    heavy = weight_hit("TCS", 16.0, threshold=12, high=15)
    assert heavy is not None and heavy.severity == "high"
    step = pledge_hit("DIXON", 12.0, 8.0, step=2.0, abs_limit=20)
    assert step is not None and "pledge" in step.title.lower()
    abs_hit = pledge_hit("X", 22.0, None, step=2.0, abs_limit=20)
    assert abs_hit is not None
    assert volume_hit("ITC", 0.3, threshold=0.45) is not None
    assert volume_hit("ITC", 0.8, threshold=0.45) is None


def test_action_regime_results_rules() -> None:
    assert action_hit("TCS", "Buy", "Hold") is not None
    assert action_hit("TCS", "Hold", "Hold") is None
    shift = regime_hit("Stress", "Calm")
    assert shift is not None and shift.symbol == "MARKET" and shift.severity == "high"
    when = datetime(2026, 8, 13)
    hit = results_hit("TCS", ["TCS Q1 profit beat"], when, when, lookback_days=5)
    assert hit is not None and hit.kind == "results"
    assert "today's news" in hit.title
    stale = results_hit("TCS", ["old"], when, datetime(2026, 7, 1), lookback_days=5)
    assert stale is None


def test_alert_service_persists_and_acks(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}", future=True)
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine, future=True)()
    account = AccountRepo(session).create("Core", "zerodha")
    repo = HoldingRepo(session)
    tcs = repo.upsert(
        account,
        MappedRow(
            symbol="TCS",
            exchange="NSE",
            quantity=Decimal("10"),
            avg_cost=Decimal("1000"),
            last_price=Decimal("3000"),
        ),
    )
    other = repo.upsert(
        account,
        MappedRow(
            symbol="ITC",
            exchange="NSE",
            quantity=Decimal("10"),
            avg_cost=Decimal("400"),
            last_price=Decimal("400"),
        ),
    )
    tcs.prev_close = Decimal("2950")
    other.prev_close = Decimal("400")
    session.add(
        Fundamental(symbol="TCS", promoter_pledge=Decimal("25"), promoter_pledge_prev=Decimal("18"))
    )
    session.add(RiskSnapshot(symbol="TCS", yahoo="TCS.NS", volume_ratio=Decimal("0.3")))
    session.add(
        Attribution(
            symbol="TCS",
            as_of=datetime(2026, 8, 1),
            action="Hold",
            reasoning="TCS is a Hold at composite 6.2. SHAP support: quality 8.8 (+1.0).",
        )
    )
    session.add(
        Attribution(
            symbol="TCS",
            as_of=datetime(2026, 8, 13),
            action="Buy",
            reasoning="TCS is a Buy at composite 7.3. SHAP support: quality 8.8 (+1.1).",
        )
    )
    session.add(
        RegimeSnapshot(
            as_of=datetime(2026, 8, 10),
            label="Calm",
            soft_calm=Decimal("1"),
            soft_elevated=Decimal("0"),
            soft_stress=Decimal("0"),
        )
    )
    session.add(
        RegimeSnapshot(
            as_of=datetime(2026, 8, 13),
            label="Elevated",
            soft_calm=Decimal("0"),
            soft_elevated=Decimal("1"),
            soft_stress=Decimal("0"),
        )
    )
    session.add(
        DailyNews(
            as_of=datetime(2026, 8, 12),
            symbol="TCS",
            title="TCS Q1 profit beat estimates",
            source="Mint",
            aspect="Results",
            kept=True,
        )
    )
    session.commit()

    result = AlertService(session).evaluate(datetime(2026, 8, 13))
    session.commit()
    kinds = {row.kind for row in AlertRepo(session).open_alerts(datetime(2026, 8, 13))}
    assert "weight" in kinds
    assert "pledge" in kinds
    assert "volume" in kinds
    assert "action" in kinds
    assert "regime" in kinds
    assert "results" in kinds
    assert result.opened >= 6

    row = next(item for item in AlertRepo(session).open_alerts() if item.kind == "action")
    assert "SHAP" in (row.shap_note or "")
    AlertRepo(session).ack(row.id)
    session.commit()
    open_kinds = {item.kind for item in AlertRepo(session).open_alerts()}
    assert "action" not in open_kinds

    WatchRepo(session).add("INFY", note="watch")
    assert WatchRepo(session).list()[0].symbol == "INFY"
    WatchRepo(session).remove("INFY")
    assert WatchRepo(session).list() == []
