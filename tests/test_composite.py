from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from meridian.data_providers.screener import parse_company_html
from meridian.scoring.composite import blend_weights, composite_score, map_action
from meridian.scoring.ownership import score_ownership
from meridian.scoring.sentiment import score_sentiment
from meridian.storage.schema import FactorScore, RegimeSnapshot

FIXTURE = Path(__file__).parent / "fixtures" / "screener_shareholding.html"


def test_parse_shareholding_and_cons() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    snap = parse_company_html(html, symbol="RELIANCE")
    assert snap.promoter_pct == Decimal("50.48")
    assert snap.fii_pct == Decimal("17.19")
    assert snap.fii_delta == Decimal("17.19") - Decimal("18.67")
    assert snap.dii_delta is not None and snap.dii_delta > 0
    assert snap.promoter_pledge == Decimal("0")
    assert len(snap.cons) == 2
    own, parts = score_ownership(snap)
    assert own is not None and Decimal("5") <= own <= Decimal("9.5")
    sent, _ = score_sentiment(snap)
    assert sent is not None and sent < Decimal("6.5")


def test_regime_blend_shifts_toward_ownership_in_stress() -> None:
    calm = RegimeSnapshot(
        as_of=datetime(2026, 8, 13),
        label="Calm",
        soft_calm=Decimal("1"),
        soft_elevated=Decimal("0"),
        soft_stress=Decimal("0"),
    )
    stress = RegimeSnapshot(
        as_of=datetime(2026, 8, 13),
        label="Stress",
        soft_calm=Decimal("0"),
        soft_elevated=Decimal("0"),
        soft_stress=Decimal("1"),
    )
    w_calm = blend_weights(calm)
    w_stress = blend_weights(stress)
    assert w_stress["ownership"] > w_calm["ownership"]
    assert w_stress["valuation"] < w_calm["valuation"]


def test_action_gates_tighten_in_stress() -> None:
    mid = Decimal("7.2")
    calm = RegimeSnapshot(
        as_of=datetime(2026, 8, 13),
        label="Calm",
        soft_calm=Decimal("1"),
        soft_elevated=Decimal("0"),
        soft_stress=Decimal("0"),
    )
    stress = RegimeSnapshot(
        as_of=datetime(2026, 8, 13),
        label="Stress",
        soft_calm=Decimal("0"),
        soft_elevated=Decimal("0"),
        soft_stress=Decimal("1"),
    )
    assert map_action(mid, calm) == "Buy"
    assert map_action(mid, stress) == "Hold"
    row = FactorScore(
        symbol="X",
        quality=Decimal("8"),
        valuation=Decimal("4"),
        technical=Decimal("6"),
        ownership=Decimal("7"),
        sentiment=Decimal("5"),
    )
    score = composite_score(row, blend_weights(calm))
    assert score is not None and Decimal("5") < score < Decimal("8")
