from __future__ import annotations

from datetime import date

from meridian_v2.hedge.engine import AssetClass, BookLeg, HedgeLeg, RegimeLabel, aggregate_exposure
from meridian_v2.hedge.vol_harvest import evaluate_vol_harvest


def test_long_gamma_delta_drift_is_vol_harvest_not_inventory():
    calls = BookLeg("c1", "GOLD", AssetClass.COMMODITY, 4, 100, 72000, delta=0.5, gamma=0.08)
    fut = HedgeLeg("f1", "GOLD", AssetClass.COMMODITY, 0, 100, 72000)
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, [calls], [fut], date.today())
    review = evaluate_vol_harvest(exp, regime=RegimeLabel.CALM, min_lots=1.0)
    assert review.policy_kind == "vol_harvest"
    assert review.net_gamma > 0
    assert review.band_breached is True
    assert "Δ REVIEW" in review.copy_review
    assert "HEDGE REVIEW" not in review.copy_review
    assert "scalping edge" not in review.copy_review.lower()


def test_short_gamma_is_warning_only():
    short = BookLeg("p1", "GOLD", AssetClass.COMMODITY, -3, 100, 72000, delta=-0.4, gamma=0.1)
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, [short], [], date.today())
    review = evaluate_vol_harvest(exp, regime=RegimeLabel.STRESS)
    assert review.short_gamma_warning is True
    assert review.drift_lots_actionable == 0
    assert "scalping edge" in review.copy_review.lower()
    assert "not" in review.copy_review.lower()
