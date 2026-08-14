from __future__ import annotations

from datetime import date

from meridian_v2.domain.copy import assert_review_copy
from meridian_v2.domain.reviews import ReviewScenario, compose_review, pick_scenario
from meridian_v2.hedge.engine import RegimeLabel
from meridian_v2.risk.greeks_book import gamma_scalp_pnl, snapshot_from_legs
from meridian_v2.risk.vega_strategies import HedgeUnit, plan_vega_actions
from meridian_v2.vega.engine import OptionGreekLeg, VegaPolicy


def _legs(*, lots=4.0, gamma=0.08, vega=60_000, theta=-1200.0, delta=0.5):
    return [
        OptionGreekLeg(
            "1",
            "GOLD",
            "GOLD26MAY 72000 CE",
            lots,
            100,
            315,
            delta,
            gamma,
            vega,
            theta_per_lot=theta,
        )
    ]


def test_gamma_scalp_sign_follows_gamma():
    long_pnl = gamma_scalp_pnl(gamma=0.32, move_inr=3.15, multiplier=100)
    short_pnl = gamma_scalp_pnl(gamma=-0.32, move_inr=3.15, multiplier=100)
    assert long_pnl > 0
    assert short_pnl < 0
    assert abs(long_pnl + short_pnl) < 1e-9


def test_snapshot_daily_pnl_is_theta():
    snap = snapshot_from_legs("GOLD", _legs(), date(2026, 8, 14))
    assert snap.delta_lots == 2.0
    assert snap.gamma == 0.32
    assert snap.vega == 240_000
    assert snap.theta == -4800.0
    assert snap.daily_pnl == snap.theta
    assert snap.long_gamma is True
    assert snap.scalp_helps is True


def test_plain_review_has_required_shape_and_no_orders():
    snap = snapshot_from_legs("GOLD", _legs(), date(2026, 8, 14))
    review = compose_review(snap, vega_limit=200_000, model_lots=-4)
    assert "(not an order)" in review.title.lower()
    assert review.daily_pnl_line.startswith("Daily PnL")
    assert review.gamma_scalp_line.startswith("Gamma Scalping PnL")
    assert "Model suggestion" in review.suggestion
    body = review.body
    assert_review_copy(body)
    assert "execute" not in body.lower()
    assert "place order" not in body.lower()


def test_scenario_matrix():
    long_pay = snapshot_from_legs("GOLD", _legs(theta=-1200), date.today())
    assert pick_scenario(long_pay, vega_limit=1_000_000) == ReviewScenario.LONG_GAMMA_THETA_COST

    # Short the same call: lots < 0 flips gamma and theta.
    short_collect = snapshot_from_legs(
        "GOLD", _legs(lots=-4, gamma=0.08, theta=-800), date.today()
    )
    assert short_collect.short_gamma
    assert short_collect.theta > 0
    assert pick_scenario(short_collect, vega_limit=1_000_000) == ReviewScenario.SHORT_GAMMA_THETA_BENEFIT

    short_pay = snapshot_from_legs(
        "GOLD", _legs(lots=-4, gamma=0.08, theta=800), date.today()
    )
    assert pick_scenario(short_pay, vega_limit=1_000_000) == ReviewScenario.SHORT_GAMMA_NEGATIVE_THETA

    over = snapshot_from_legs("GOLD", _legs(), date.today())
    assert pick_scenario(over, vega_limit=200_000) == ReviewScenario.OVER_LIMIT_VEGA


def test_vega_actions_include_cross_greeks_and_six_keys():
    snap = snapshot_from_legs("GOLD", _legs(), date.today())
    policy = VegaPolicy("GOLD", 200_000, hedge_vega_per_lot=55_000, hedge_delta=0.48, lot_step=1)
    unit = HedgeUnit(vega=55_000, delta=0.48, gamma=0.02, theta=-800)
    actions = plan_vega_actions(
        snap,
        policy,
        unit,
        regime=RegimeLabel.STRESS,
        days_to_expiry=10,
        peer_vega=(("SILVER", -80_000),),
    )
    keys = [item.key for item in actions]
    assert keys == [
        "limit_cap",
        "cut_options",
        "hedge_options",
        "book_balance",
        "regime_limit",
        "time_reduce",
    ]
    live = [item for item in actions if item.enabled]
    assert live
    for item in live:
        assert item.d_vega == item.opt_lots * 55_000
        assert item.d_delta == item.opt_lots * 0.48
        assert item.d_gamma == item.opt_lots * 0.02
        assert item.d_theta == item.opt_lots * -800


def test_every_template_scenario_renders():
    snap = snapshot_from_legs("GOLD", _legs(), date.today())
    for scenario in ReviewScenario:
        review = compose_review(snap, scenario=scenario, model_lots=-2)
        assert "(not an order)" in review.title.lower()
        assert review.daily_pnl_line
        assert review.gamma_scalp_line
        assert_review_copy(review.body)


def test_desk_review_includes_scalp_and_six_actions(session):
    from meridian_v2.risk.review_service import build_desk_review
    from meridian_v2.storage.seed import seed_demo

    seed_demo(session, reset=True)
    payload = build_desk_review(session, "GOLD")
    assert payload["review"]["title"]
    assert "(not an order)" in payload["review"]["title"].lower()
    assert payload["greeks"]["daily_pnl"] == payload["greeks"]["theta"]
    assert "gamma_sign" in payload["greeks"]
    assert payload["gamma_scalp"]["steps"]
    assert len(payload["actions"]) == 6
    assert {item["key"] for item in payload["actions"]} >= {
        "limit_cap",
        "cut_options",
        "hedge_options",
        "book_balance",
        "regime_limit",
        "time_reduce",
    }
    for item in payload["actions"]:
        assert "delta" in item["effects"]
        assert "gamma" in item["effects"]
        assert "vega" in item["effects"]
        assert "theta" in item["effects"]
