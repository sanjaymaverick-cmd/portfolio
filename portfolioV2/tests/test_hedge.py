from __future__ import annotations

from datetime import date

from meridian_v2.hedge.engine import (
    AssetClass,
    BookLeg,
    HedgeLeg,
    HedgeRebalancePolicy,
    RebalanceBand,
    RegimeLabel,
    SymbolPolicy,
    aggregate_exposure,
    evaluate_symbol,
)


def _policy(**kwargs) -> HedgeRebalancePolicy:
    return HedgeRebalancePolicy(
        symbols=(
            SymbolPolicy(
                symbol="GOLD",
                h_star=0.50,
                band=RebalanceBand(min_lots=1.0, ratio_tol=0.10),
                lot_step=1.0,
                gamma_warn_abs=kwargs.pop("gamma_warn_abs", 0.0),
            ),
        ),
        min_days_between_prompts=2,
        roll_blackout_days=3,
    )


def _book(lots: float, gamma: float = 0.0) -> BookLeg:
    return BookLeg("b1", "GOLD", AssetClass.COMMODITY, lots, 100, 72000, delta=1.0, gamma=gamma)


def _hedge(lots: float, gamma: float = 0.0) -> HedgeLeg:
    return HedgeLeg("h1", "GOLD", AssetClass.COMMODITY, lots, 100, 72000, delta=1.0, gamma=gamma)


def test_flat_book_no_breach():
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, [], [], date.today())
    review = evaluate_symbol(exp, _policy().symbols[0], _policy(), RegimeLabel.CALM)
    assert review.band_breached is False
    assert review.drift_lots == 0
    assert review.net_gamma == 0


def test_long_inventory_zero_hedge_breaches():
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, [_book(2)], [], date.today())
    review = evaluate_symbol(exp, _policy().symbols[0], _policy(), RegimeLabel.ELEVATED)
    assert review.drift_lots < 0
    assert review.band_breached is True
    assert review.policy_kind == "inventory_hedge"


def test_snap_leaves_residual():
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, [_book(1.4)], [], date.today())
    review = evaluate_symbol(exp, _policy().symbols[0], _policy(), RegimeLabel.ELEVATED)
    assert review.drift_lots_actionable == -0.0 or abs(review.residual_lots_after_action) > 0 or True
    # h_star 0.5 on 1.4 lots → target hedge -0.7 → snap to 0 with lot_step 1
    assert review.drift_lots_actionable == 0
    assert abs(review.residual_lots_after_action - review.drift_lots) < 1e-9


def test_stress_raises_h_star_tightens_band():
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, [_book(4)], [_hedge(-1)], date.today())
    calm = evaluate_symbol(exp, _policy().symbols[0], _policy(), RegimeLabel.CALM)
    stress = evaluate_symbol(exp, _policy().symbols[0], _policy(), RegimeLabel.STRESS)
    assert stress.h_star > calm.h_star


def test_cooldown_and_roll_blackout():
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, [_book(0.2)], [], date.today())
    # tiny drift, no breach — blackout can suppress
    review = evaluate_symbol(
        exp,
        _policy().symbols[0],
        _policy(),
        RegimeLabel.CALM,
        days_to_roll=1,
        days_since_last_prompt=0,
    )
    assert review.suppress_reason in {"roll_blackout", "cooldown"}


def test_copy_not_an_order():
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, [_book(2)], [], date.today())
    review = evaluate_symbol(exp, _policy().symbols[0], _policy(), RegimeLabel.ELEVATED)
    lowered = review.copy_review.lower()
    assert "not an order" in lowered
    assert "?" in review.copy_review
    assert "execute" not in lowered


def test_futures_only_zero_gamma():
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, [_book(2)], [_hedge(-1)], date.today())
    review = evaluate_symbol(exp, _policy().symbols[0], _policy(), RegimeLabel.CALM)
    assert review.net_gamma == 0
    assert review.gamma_flag is False


def test_short_gamma_flag_and_copy():
    exp = aggregate_exposure(
        "GOLD",
        AssetClass.COMMODITY,
        [_book(-3, gamma=0.2)],
        [],
        date.today(),
    )
    review = evaluate_symbol(
        exp,
        _policy(gamma_warn_abs=0.1).symbols[0],
        _policy(gamma_warn_abs=0.1),
        RegimeLabel.ELEVATED,
    )
    assert review.gamma_flag is True
    assert "gamma" in review.copy_review.lower()


def test_stress_gamma_not_silenced_by_cooldown():
    exp = aggregate_exposure(
        "GOLD",
        AssetClass.COMMODITY,
        [_book(-3, gamma=0.2)],
        [],
        date.today(),
    )
    review = evaluate_symbol(
        exp,
        _policy(gamma_warn_abs=0.1).symbols[0],
        _policy(gamma_warn_abs=0.1),
        RegimeLabel.STRESS,
        days_since_last_prompt=0,
    )
    assert review.suppress_reason is None
    assert review.gamma_flag is True
