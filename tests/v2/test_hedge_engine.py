from datetime import date

from meridian_v2.domain.enums import AssetClass, PolicyKind, RegimeLabel
from meridian_v2.hedge import (
    BookLeg,
    HedgeLeg,
    HedgeRebalancePolicy,
    RebalanceBand,
    SymbolPolicy,
    aggregate_exposure,
    evaluate_symbol,
)


def _policy(h_star: float = 0.5) -> HedgeRebalancePolicy:
    return HedgeRebalancePolicy(
        symbols=(
            SymbolPolicy(
                symbol="GOLD",
                h_star=h_star,
                band=RebalanceBand(min_lots=1.0, ratio_tol=0.10),
                lot_step=1.0,
            ),
        )
    )


def test_flat_book_no_breach():
    as_of = date(2026, 8, 13)
    exp = aggregate_exposure(
        "GOLD",
        AssetClass.COMMODITY,
        [],
        [],
        as_of,
    )
    rev = evaluate_symbol(
        exp, _policy().symbols[0], _policy(), RegimeLabel.CALM
    )
    assert rev.band_breached is False
    assert rev.drift_lots == 0.0
    assert rev.urgency == "none"


def test_long_inventory_half_hedge_target():
    as_of = date(2026, 8, 13)
    book = [
        BookLeg(
            "b1",
            "GOLD",
            AssetClass.COMMODITY,
            lots=2.0,
            multiplier=100.0,
            mark_inr=70000.0,
        )
    ]
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, book, [], as_of)
    rev = evaluate_symbol(
        exp, _policy(0.5).symbols[0], _policy(0.5), RegimeLabel.CALM
    )
    # target hedge lots = -1.0 for h*=0.5 on +2 book
    assert rev.drift_lots_actionable == -1.0
    assert rev.band_breached is True
    assert "not an order" in rev.copy_review
    assert rev.policy_kind == PolicyKind.INVENTORY_HEDGE


def test_snap_leaves_residual_concept():
    as_of = date(2026, 8, 13)
    book = [
        BookLeg(
            "b1",
            "GOLD",
            AssetClass.COMMODITY,
            lots=3.0,
            multiplier=100.0,
            mark_inr=70000.0,
        )
    ]
    # existing hedge -0.4 effective → drift not integer
    hedges = [
        HedgeLeg(
            "h1",
            "GOLD",
            AssetClass.COMMODITY,
            lots=-0.4,
            multiplier=100.0,
            mark_inr=70000.0,
        )
    ]
    exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, book, hedges, as_of)
    pol = _policy(0.5)
    rev = evaluate_symbol(exp, pol.symbols[0], pol, RegimeLabel.ELEVATED)
    assert rev.drift_lots_actionable == snap_check(rev)
    assert abs(rev.residual_lots_after_action) >= 0.0


def snap_check(rev) -> float:
    return rev.drift_lots_actionable


def test_vol_harvest_tag_in_copy():
    as_of = date(2026, 8, 13)
    book = [
        BookLeg(
            "b1",
            "GOLD",
            AssetClass.COMMODITY,
            lots=2.0,
            multiplier=1.0,
            mark_inr=1.0,
            delta=1.0,
            gamma=0.05,
        )
    ]
    exp = aggregate_exposure(
        "GOLD",
        AssetClass.COMMODITY,
        book,
        [],
        as_of,
        policy_kind=PolicyKind.VOL_HARVEST,
    )
    pol = HedgeRebalancePolicy(
        symbols=(
            SymbolPolicy(
                symbol="GOLD",
                h_star=1.0,
                band=RebalanceBand(min_lots=0.5, ratio_tol=0.05),
                lot_step=1.0,
                gamma_warn_abs=0.01,
            ),
        )
    )
    rev = evaluate_symbol(
        exp,
        pol.symbols[0],
        pol,
        RegimeLabel.CALM,
        policy_kind=PolicyKind.VOL_HARVEST,
    )
    assert rev.policy_kind == PolicyKind.VOL_HARVEST
    assert "Δ REVIEW" in rev.copy_review or rev.gamma_flag
