from __future__ import annotations

from datetime import date

from meridian_v2.vega.engine import OptionGreekLeg, VegaPolicy, aggregate_vega, evaluate_vega


def test_example_a_long_over_limit_sell():
    legs = [
        OptionGreekLeg("1", "GOLD", "GOLD26MAY 72000 CE", 4, 100, 315, 0.50, 0.08, 60_000, iv=0.16)
    ]
    exp = aggregate_vega("GOLD", legs, date.today())
    assert exp.net_vega == 240_000
    pol = VegaPolicy("GOLD", 200_000, hedge_vega_per_lot=55_000, hedge_delta=0.48, lot_step=1)
    review = evaluate_vega(exp, pol, hedge_vega_per_lot=55_000, hedge_delta=0.48)
    assert review.over_limit is True
    assert review.opt_lots_actionable == -4
    assert review.futures_delta_lots == 0
    assert "VEGA REVIEW" in review.copy_review
    assert "not an order" in review.copy_review.lower()


def test_example_b_short_stress_buy():
    legs = [
        OptionGreekLeg("1", "GOLD", "GOLD PUT", -3, 100, 200, 0.40, 0.1, 50_000)
    ]
    exp = aggregate_vega("GOLD", legs, date.today())
    assert exp.net_vega == -150_000
    pol = VegaPolicy("GOLD", 100_000, hedge_vega_per_lot=50_000, hedge_delta=-0.40, lot_step=1)
    review = evaluate_vega(
        exp, pol, hedge_vega_per_lot=50_000, hedge_delta=-0.40, regime_stress=True
    )
    assert review.opt_lots_actionable == 3
    assert review.urgency == "elevated"


def test_example_c_under_limit_no_flatten():
    legs = [
        OptionGreekLeg("1", "GOLD", "STRADDLE", 2, 100, 400, 0.70, 0.1, 60_000)
    ]
    exp = aggregate_vega("GOLD", legs, date.today())
    assert exp.net_vega == 120_000
    pol = VegaPolicy("GOLD", 200_000, warn_utilization=0.80, hedge_vega_per_lot=55_000)
    review = evaluate_vega(exp, pol, hedge_vega_per_lot=55_000)
    assert review.over_limit is False
    assert review.opt_lots_actionable == 0
    assert review.urgency == "none"


def test_stale_greeks_mute_lots():
    legs = [
        OptionGreekLeg("1", "GOLD", "CE", 4, 100, 315, 0.5, 0.08, 60_000, stale=True)
    ]
    exp = aggregate_vega("GOLD", legs, date.today())
    pol = VegaPolicy("GOLD", 200_000, hedge_vega_per_lot=55_000)
    review = evaluate_vega(exp, pol, hedge_vega_per_lot=55_000)
    assert review.opt_lots_actionable == 0
    assert "stale" in review.copy_review.lower()
