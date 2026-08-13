"""Vol harvest — separate policy stream. Target net Δ near 0 on a long-gamma book."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from meridian_v2.hedge.engine import HedgeExposure, RegimeLabel, snap_lots


@dataclass(frozen=True)
class VolHarvestReview:
    symbol: str
    as_of: date
    regime: RegimeLabel
    net_delta_lots: float
    net_gamma: float
    drift_lots: float
    drift_lots_actionable: float
    band_breached: bool
    gamma_flag: bool
    short_gamma_warning: bool
    urgency: str
    reason: str
    copy_review: str
    suppress_reason: Optional[str] = None
    policy_kind: str = "vol_harvest"


def build_delta_copy(
    symbol: str,
    exposure: HedgeExposure,
    drift_actionable: float,
    regime: RegimeLabel,
    *,
    short_gamma: bool,
) -> str:
    if short_gamma:
        return (
            f"Δ RISK NOTE — not an order, not a scalping edge. {symbol}: net gamma is short "
            f"({exposure.net_gamma:+.4f}) with net Δ {exposure.net_lots:+.2f} lots ({regime.value}). "
            f"Short gamma can run against the book on a gap. Review residual risk; "
            f"do not treat this as a harvest."
        )
    direction = "sell" if drift_actionable < 0 else "buy" if drift_actionable > 0 else "hold"
    return (
        f"Δ REVIEW — not an order. {symbol}: long-gamma book, net Δ {exposure.net_lots:+.2f} lots "
        f"vs target ~0 ({regime.value}). Model futures step {drift_actionable:+.2f} lots "
        f"(consider a {direction} of that size). "
        f"Review whether to flatten residual delta, wait, or accept the drift?"
    )


def evaluate_vol_harvest(
    exposure: HedgeExposure,
    *,
    regime: RegimeLabel,
    min_lots: float = 1.0,
    lot_step: float = 1.0,
    days_since_last_prompt: Optional[int] = None,
    min_days_between_prompts: int = 2,
    force: bool = False,
) -> VolHarvestReview:
    net_delta = exposure.net_lots
    drift = -net_delta
    actionable = snap_lots(drift, lot_step)
    long_gamma = exposure.net_gamma > 1e-12
    short_gamma = exposure.net_gamma < -1e-12
    breached = abs(drift) >= min_lots
    gamma_flag = abs(exposure.net_gamma) > 1e-12

    suppress: Optional[str] = None
    if not force and days_since_last_prompt is not None:
        if days_since_last_prompt < min_days_between_prompts:
            if not (short_gamma and regime == RegimeLabel.STRESS):
                suppress = "cooldown"

    if not long_gamma and not short_gamma:
        return VolHarvestReview(
            symbol=exposure.symbol,
            as_of=exposure.as_of,
            regime=regime,
            net_delta_lots=net_delta,
            net_gamma=exposure.net_gamma,
            drift_lots=0.0,
            drift_lots_actionable=0.0,
            band_breached=False,
            gamma_flag=False,
            short_gamma_warning=False,
            urgency="none",
            reason="zero_gamma",
            copy_review="",
            suppress_reason="zero_gamma",
        )

    urgency = "none"
    if suppress is None and (breached or short_gamma):
        if short_gamma:
            urgency = "elevated" if regime == RegimeLabel.STRESS else "review"
        elif long_gamma and breached:
            urgency = "elevated" if regime == RegimeLabel.STRESS else "review"

    copy = ""
    if urgency != "none":
        copy = build_delta_copy(
            exposure.symbol, exposure, actionable, regime, short_gamma=short_gamma
        )

    return VolHarvestReview(
        symbol=exposure.symbol,
        as_of=exposure.as_of,
        regime=regime,
        net_delta_lots=net_delta,
        net_gamma=exposure.net_gamma,
        drift_lots=drift if long_gamma else 0.0,
        drift_lots_actionable=actionable if long_gamma else 0.0,
        band_breached=breached and long_gamma,
        gamma_flag=gamma_flag,
        short_gamma_warning=short_gamma,
        urgency=urgency if suppress is None else "none",
        reason=(
            f"net_delta={net_delta:.3f}; net_gamma={exposure.net_gamma:.6f}; "
            f"long_gamma={long_gamma}; short_gamma={short_gamma}; breached={breached}"
        ),
        copy_review=copy,
        suppress_reason=suppress,
        policy_kind="vol_harvest",
    )
