from datetime import date

from meridian_v2.domain.enums import PolicyKind
from meridian_v2.vega import (
    OptionGreekLeg,
    VegaPolicy,
    aggregate_vega,
    evaluate_vega,
)


def test_under_limit_no_actionable_lots():
    as_of = date(2026, 8, 13)
    legs = [
        OptionGreekLeg(
            "1",
            "GOLD",
            "C1",
            lots=2.0,
            multiplier=1.0,
            mark_inr=1.0,
            delta=0.5,
            gamma=0.01,
            vega_per_lot=50_000,
        )
    ]
    exp = aggregate_vega("GOLD", legs, as_of)
    assert exp.net_vega == 100_000
    pol = VegaPolicy(symbol="GOLD", vega_limit=200_000)
    rev = evaluate_vega(exp, pol, hedge_vega_per_lot=50_000)
    assert rev.over_limit is False
    assert rev.opt_lots_actionable == 0.0
    assert rev.urgency == "none"


def test_long_over_limit_sells_options():
    as_of = date(2026, 8, 13)
    legs = [
        OptionGreekLeg(
            "1",
            "GOLD",
            "C1",
            lots=4.0,
            multiplier=1.0,
            mark_inr=1.0,
            delta=0.5,
            gamma=0.01,
            vega_per_lot=60_000,
        )
    ]
    exp = aggregate_vega("GOLD", legs, as_of)
    pol = VegaPolicy(symbol="GOLD", vega_limit=200_000, lot_step=1.0)
    rev = evaluate_vega(exp, pol, hedge_vega_per_lot=55_000, hedge_delta=0.48)
    assert rev.over_limit is True
    assert rev.opt_lots_actionable < 0
    assert "not an order" in rev.copy_review
    assert rev.policy_kind == PolicyKind.VEGA_DEFENSE


def test_warn_level_no_trade_copy_has_no_zero_lot_advice():
    # Utilization at/above warn but under the limit, not forced: a heads-up
    # review is emitted, but it must not advise a +0.0-lot hedge.
    as_of = date(2026, 8, 13)
    legs = [
        OptionGreekLeg(
            "1",
            "GOLD",
            "C1",
            lots=1.7,
            multiplier=1.0,
            mark_inr=1.0,
            delta=0.5,
            gamma=0.01,
            vega_per_lot=50_000,
        )
    ]
    exp = aggregate_vega("GOLD", legs, as_of)
    assert exp.net_vega == 85_000  # util = 0.85, >= warn 0.80, under limit
    pol = VegaPolicy(symbol="GOLD", vega_limit=100_000, warn_utilization=0.80)
    rev = evaluate_vega(exp, pol, hedge_vega_per_lot=50_000)
    assert rev.over_limit is False
    assert rev.urgency == "review"
    assert rev.opt_lots_actionable == 0.0
    assert rev.futures_delta_lots == 0.0
    assert rev.copy_review  # non-empty heads-up
    assert "+0.0 lots" not in rev.copy_review
    assert "No hedge sized" in rev.copy_review


def test_short_over_limit_buys_options():
    as_of = date(2026, 8, 13)
    legs = [
        OptionGreekLeg(
            "1",
            "GOLD",
            "P1",
            lots=-3.0,
            multiplier=1.0,
            mark_inr=1.0,
            delta=-0.4,
            gamma=-0.02,
            vega_per_lot=50_000,
        )
    ]
    exp = aggregate_vega("GOLD", legs, as_of)
    assert exp.net_vega == -150_000
    pol = VegaPolicy(symbol="GOLD", vega_limit=100_000)
    rev = evaluate_vega(
        exp, pol, hedge_vega_per_lot=50_000, hedge_delta=-0.4, regime_stress=True
    )
    assert rev.opt_lots_actionable > 0
    assert rev.urgency == "elevated"
