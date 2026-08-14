from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from meridian.domain.models import MappedRow
from meridian.recommendations.copy import portfolio_note, write_reasoning
from meridian.recommendations.shap_explain import explain, linear_shap
from meridian.scoring.composite import DEFAULT_WEIGHTS, composite_score
from meridian.storage.repositories import AccountRepo, HoldingRepo
from meridian.storage.schema import Base, FactorScore, RegimeSnapshot


def test_linear_shap_adds_up() -> None:
    row = FactorScore(
        symbol="AAA",
        quality=Decimal("8.0"),
        valuation=Decimal("4.0"),
        technical=Decimal("6.0"),
        ownership=Decimal("7.0"),
        sentiment=Decimal("5.0"),
    )
    weights = {key: Decimal(str(value)) for key, value in DEFAULT_WEIGHTS["Calm"].items()}
    result = linear_shap(row, weights)
    recon = result.base + sum(result.phis.values())
    score = float(composite_score(row, weights) or 0)
    assert abs(recon - score) < 1e-6
    assert result.phis["quality"] > 0
    assert result.phis["valuation"] < 0


def test_reasoning_cites_shap_drivers() -> None:
    row = FactorScore(
        symbol="TCS",
        quality=Decimal("8.8"),
        valuation=Decimal("4.0"),
        technical=Decimal("7.5"),
        ownership=Decimal("7.0"),
        sentiment=Decimal("3.5"),
        composite=Decimal("6.8"),
        action="Hold",
        confidence=Decimal("0.7"),
    )
    weights = {key: Decimal(str(value)) for key, value in DEFAULT_WEIGHTS["Calm"].items()}
    shap = explain(row, weights)
    text, note = write_reasoning(
        symbol="TCS",
        action="Hold",
        composite=row.composite,
        confidence=row.confidence,
        regime="Calm",
        row=row,
        shap=shap,
        weight=Decimal("9.5"),
        top_symbol="TCS",
        names=17,
    )
    assert "Hold" in text and "Calm" in text
    assert "SHAP" in text or "quality" in text
    assert "not an order" in text
    assert "9.5%" in note


def test_portfolio_note_flags_concentration() -> None:
    assert "large slice" in portfolio_note("X", Decimal("15"), "X", 10)
    assert "17-name" in portfolio_note("Y", Decimal("3.2"), "X", 17)


def test_explain_service_persists(tmp_path: Path) -> None:
    from meridian.recommendations.service import ExplainService

    engine = create_engine(f"sqlite:///{tmp_path / 'e.db'}", future=True)
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine, future=True)()
    account = AccountRepo(session).create("Core", "zerodha")
    HoldingRepo(session).upsert(
        account,
        MappedRow(
            symbol="AAA",
            exchange="NSE",
            quantity=Decimal("10"),
            avg_cost=Decimal("100"),
            last_price=Decimal("120"),
        ),
    )
    session.add(
        FactorScore(
            symbol="AAA",
            quality=Decimal("8"),
            valuation=Decimal("5"),
            technical=Decimal("6"),
            ownership=Decimal("7"),
            sentiment=Decimal("5"),
            composite=Decimal("6.5"),
            action="Hold",
            confidence=Decimal("0.6"),
        )
    )
    session.add(
        RegimeSnapshot(
            as_of=datetime(2026, 8, 13),
            label="Calm",
            soft_calm=Decimal("1"),
            soft_elevated=Decimal("0"),
            soft_stress=Decimal("0"),
        )
    )
    session.commit()
    written = ExplainService(session).explain_all("AAA")
    assert written == 1
    row = ExplainService(session).attributions.latest("AAA")
    assert row is not None
    assert row.reasoning
    assert row.phis
    assert "AAA" in (row.portfolio_note or "")
