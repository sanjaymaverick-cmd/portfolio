from __future__ import annotations

from datetime import date

from meridian_v2.risk.gamma_scalp import explain_scalp
from meridian_v2.risk.greeks_book import snapshot_from_legs
from meridian_v2.vega.engine import OptionGreekLeg


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


def test_long_gamma_loop_helps_and_covers_steps():
    snap = snapshot_from_legs("GOLD", _legs(), date(2026, 8, 14))
    report = explain_scalp(snap)
    assert report.helps is True
    assert report.hurts is False
    assert report.posture == "long"
    assert len(report.steps) == 3
    up = report.steps[1]
    down = report.steps[2]
    assert up.delta_lots > 0
    assert down.delta_lots < 0
    assert up.hedge_lots < 0
    assert down.hedge_lots > 0
    assert report.scalp_pnl_on_move > 0
    assert "helping" in report.gamma_scalp_line.lower()
    assert "(not an order)" in report.title.lower()


def test_short_gamma_loop_hurts_and_is_not_a_harvest():
    snap = snapshot_from_legs("GOLD", _legs(lots=-4, gamma=0.08, theta=-800), date(2026, 8, 14))
    report = explain_scalp(snap)
    assert report.hurts is True
    assert report.helps is False
    assert report.scalp_pnl_on_move < 0
    assert "not a harvest" in report.suggestion.lower()
    assert "hurts" in report.gamma_scalp_line.lower()
    up = report.steps[1]
    assert up.delta_lots < 0
    assert up.hedge_lots > 0


def test_rehedge_band_uses_current_residual():
    snap = snapshot_from_legs("GOLD", _legs(delta=0.6, lots=4), date(2026, 8, 14))
    assert abs(snap.delta_lots) >= 1.0
    report = explain_scalp(snap, rehedge_band_lots=1.0)
    assert report.needs_rehedge is True
    assert report.suggested_futures_lots == -2.0


def test_flat_gamma_has_no_scalp_story():
    snap = snapshot_from_legs(
        "GOLD",
        _legs(gamma=0.0, delta=0.0, lots=1, theta=0),
        date(2026, 8, 14),
    )
    report = explain_scalp(snap)
    assert report.helps is False
    assert report.hurts is False
    assert report.scalp_pnl_on_move == 0
    assert "no scalp story" in report.status_lines[1].lower() or "flat" in report.status_lines[1].lower()
