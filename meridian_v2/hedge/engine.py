"""Pure inventory-hedge engine — no broker.

Normative design: docs/v2/HEDGE_REBALANCE_SKETCH.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional, Sequence

from meridian_v2.domain.enums import AssetClass, PolicyKind, RegimeLabel


@dataclass(frozen=True)
class BookLeg:
    leg_id: str
    symbol: str
    asset_class: AssetClass
    lots: float
    multiplier: float
    mark_inr: float
    contract_label: str = ""
    delta: float = 1.0
    gamma: float = 0.0
    as_of: Optional[date] = None

    @property
    def effective_lots(self) -> float:
        return self.lots * self.delta

    @property
    def notional_inr(self) -> float:
        # Delta-adjusted, matching HedgeLeg, so book_notional and hedge_notional
        # share one convention and hedge_ratio compares like-for-like risk.
        # For linear legs (delta=1.0) this is identical to lots * multiplier * mark.
        return self.effective_lots * self.multiplier * self.mark_inr

    @property
    def gamma_lots(self) -> float:
        return self.lots * self.gamma


@dataclass(frozen=True)
class HedgeLeg:
    leg_id: str
    symbol: str
    asset_class: AssetClass
    lots: float
    multiplier: float
    mark_inr: float
    contract_label: str = ""
    delta: float = 1.0
    gamma: float = 0.0
    as_of: Optional[date] = None

    @property
    def effective_lots(self) -> float:
        return self.lots * self.delta

    @property
    def notional_inr(self) -> float:
        return self.effective_lots * self.multiplier * self.mark_inr

    @property
    def gamma_lots(self) -> float:
        return self.lots * self.gamma


@dataclass(frozen=True)
class HedgeExposure:
    symbol: str
    asset_class: AssetClass
    book_lots: float
    book_notional_inr: float
    hedge_lots: float
    hedge_notional_inr: float
    as_of: date
    contract_notes: str = ""
    net_gamma: float = 0.0
    policy_kind: PolicyKind = PolicyKind.INVENTORY_HEDGE

    @property
    def net_lots(self) -> float:
        return self.book_lots + self.hedge_lots

    @property
    def net_notional_inr(self) -> float:
        return self.book_notional_inr + self.hedge_notional_inr

    @property
    def hedge_ratio(self) -> Optional[float]:
        if abs(self.book_notional_inr) < 1e-6:
            return None
        return float(-self.hedge_notional_inr / self.book_notional_inr)


@dataclass(frozen=True)
class RebalanceBand:
    min_lots: float = 1.0
    ratio_tol: float = 0.10
    min_notional_inr: float = 0.0


@dataclass(frozen=True)
class SymbolPolicy:
    symbol: str
    h_star: float
    band: RebalanceBand = field(default_factory=RebalanceBand)
    lot_step: float = 1.0
    enabled: bool = True
    gamma_warn_abs: float = 0.0


@dataclass(frozen=True)
class RegimeOverride:
    h_star_scale: float = 1.0
    band_scale: float = 1.0


@dataclass(frozen=True)
class HedgeRebalancePolicy:
    symbols: tuple[SymbolPolicy, ...]
    regime_overrides: dict[RegimeLabel, RegimeOverride] = field(
        default_factory=lambda: {
            RegimeLabel.CALM: RegimeOverride(h_star_scale=1.0, band_scale=1.3),
            RegimeLabel.ELEVATED: RegimeOverride(h_star_scale=1.0, band_scale=1.0),
            RegimeLabel.STRESS: RegimeOverride(h_star_scale=1.2, band_scale=0.7),
        }
    )
    min_days_between_prompts: int = 2
    roll_blackout_days: int = 3


@dataclass(frozen=True)
class HedgeReview:
    symbol: str
    as_of: date
    regime: RegimeLabel
    policy_kind: PolicyKind
    h_star: float
    h_actual: Optional[float]
    book_lots: float
    hedge_lots: float
    drift_lots: float
    drift_lots_actionable: float
    residual_lots_after_action: float
    band_breached: bool
    urgency: str
    reason: str
    copy_review: str
    suppress_reason: Optional[str] = None
    net_gamma: float = 0.0
    gamma_flag: bool = False


def aggregate_exposure(
    symbol: str,
    asset_class: AssetClass,
    book_legs: Sequence[BookLeg],
    hedge_legs: Sequence[HedgeLeg],
    as_of: date,
    contract_notes: str = "",
    policy_kind: PolicyKind = PolicyKind.INVENTORY_HEDGE,
) -> HedgeExposure:
    b = [x for x in book_legs if x.symbol == symbol]
    h = [x for x in hedge_legs if x.symbol == symbol]
    return HedgeExposure(
        symbol=symbol,
        asset_class=asset_class,
        book_lots=sum(x.effective_lots for x in b),
        book_notional_inr=sum(x.notional_inr for x in b),
        hedge_lots=sum(x.effective_lots for x in h),
        hedge_notional_inr=sum(x.notional_inr for x in h),
        as_of=as_of,
        contract_notes=contract_notes,
        net_gamma=sum(x.gamma_lots for x in b) + sum(x.gamma_lots for x in h),
        policy_kind=policy_kind,
    )


def effective_target(
    base_h_star: float, regime: RegimeLabel, policy: HedgeRebalancePolicy
) -> float:
    ov = policy.regime_overrides.get(regime, RegimeOverride())
    return float(min(1.0, max(0.0, base_h_star * ov.h_star_scale)))


def effective_band(
    band: RebalanceBand, regime: RegimeLabel, policy: HedgeRebalancePolicy
) -> RebalanceBand:
    ov = policy.regime_overrides.get(regime, RegimeOverride())
    s = ov.band_scale
    return RebalanceBand(
        min_lots=band.min_lots * s,
        ratio_tol=band.ratio_tol * s,
        min_notional_inr=band.min_notional_inr * s,
    )


def target_hedge_lots(exposure: HedgeExposure, h_star: float) -> float:
    if abs(exposure.book_lots) < 1e-12:
        return 0.0
    npl = exposure.book_notional_inr / exposure.book_lots
    target_hedge_notional = -h_star * exposure.book_notional_inr
    return target_hedge_notional / npl if abs(npl) > 1e-12 else 0.0


def lot_drift(exposure: HedgeExposure, h_star: float) -> float:
    return target_hedge_lots(exposure, h_star) - exposure.hedge_lots


def snap_lots(raw: float, lot_step: float) -> float:
    if lot_step <= 0:
        return raw
    return math.copysign(math.floor(abs(raw) / lot_step + 1e-12) * lot_step, raw)


def band_breached(
    exposure: HedgeExposure, h_star: float, band: RebalanceBand, drift: float
) -> bool:
    # Two independent triggers: absolute lot drift and ratio deviation. Either
    # one breaches the band. (Ratio deviation has no meaning without book
    # exposure, so it can only fire when hedge_ratio is defined.)
    h_act = exposure.hedge_ratio
    lot_breach = abs(drift) >= band.min_lots
    ratio_breach = h_act is not None and abs(h_act - h_star) > band.ratio_tol
    if not (lot_breach or ratio_breach):
        return False
    # ₹ floor: suppress an otherwise-breaching drift whose notional impact is
    # below the configured minimum.
    if band.min_notional_inr > 0 and abs(exposure.book_lots) > 1e-12:
        npl = exposure.book_notional_inr / exposure.book_lots
        if abs(drift * npl) < band.min_notional_inr:
            return False
    return True


def build_review_copy(
    symbol: str,
    exposure: HedgeExposure,
    h_star: float,
    h_actual: Optional[float],
    drift_actionable: float,
    residual: float,
    regime: RegimeLabel,
    *,
    policy_kind: PolicyKind = PolicyKind.INVENTORY_HEDGE,
    gamma_flag: bool = False,
) -> str:
    h_txt = f"{h_actual:.0%}" if h_actual is not None else "n/a"
    direction = (
        "increase" if drift_actionable > 0 else "reduce" if drift_actionable < 0 else "hold"
    )
    label = (
        "HEDGE REVIEW"
        if policy_kind == PolicyKind.INVENTORY_HEDGE
        else "Δ REVIEW"
    )
    gamma_bit = ""
    if gamma_flag:
        sign = "long" if exposure.net_gamma > 0 else "short"
        gamma_bit = (
            f" Net gamma is {sign} ({exposure.net_gamma:+.4f}) — delta may drift "
            f"quickly if the underlier gaps; review residual risk."
        )
    return (
        f"{label} — not an order. [{policy_kind.value}] {symbol}: book {exposure.book_lots:+.2f} lots, "
        f"hedge {exposure.hedge_lots:+.2f} lots, ratio {h_txt} vs target {h_star:.0%} "
        f"({regime.value}). Model drift {drift_actionable:+.2f} lots ({direction}); "
        f"residual after step {residual:+.2f} lots."
        f"{gamma_bit} "
        f"Review whether to adjust, wait for roll, or accept residual risk?"
    )


def evaluate_symbol(
    exposure: HedgeExposure,
    symbol_policy: SymbolPolicy,
    policy: HedgeRebalancePolicy,
    regime: RegimeLabel,
    *,
    policy_kind: PolicyKind = PolicyKind.INVENTORY_HEDGE,
    days_since_last_prompt: Optional[int] = None,
    days_to_roll: Optional[int] = None,
    force: bool = False,
) -> HedgeReview:
    if not symbol_policy.enabled:
        return _suppressed(
            exposure, symbol_policy, policy, regime, policy_kind, "symbol_disabled"
        )

    h_star = effective_target(symbol_policy.h_star, regime, policy)
    band = effective_band(symbol_policy.band, regime, policy)
    drift = lot_drift(exposure, h_star)
    actionable = snap_lots(drift, symbol_policy.lot_step)
    residual = drift - actionable
    breached = band_breached(exposure, h_star, band, drift)
    gamma_flag = (
        symbol_policy.gamma_warn_abs > 0
        and abs(exposure.net_gamma) >= symbol_policy.gamma_warn_abs
    )

    suppress: Optional[str] = None
    if not force:
        if (
            days_to_roll is not None
            and 0 <= days_to_roll <= policy.roll_blackout_days
            and not breached
            and not gamma_flag
        ):
            suppress = "roll_blackout"
        if (
            days_since_last_prompt is not None
            and days_since_last_prompt < policy.min_days_between_prompts
        ):
            if not (gamma_flag and regime == RegimeLabel.STRESS):
                suppress = suppress or "cooldown"

    urgency = "none"
    if (breached or gamma_flag) and suppress is None:
        urgency = "elevated" if regime == RegimeLabel.STRESS or gamma_flag else "review"

    h_act = exposure.hedge_ratio
    copy = build_review_copy(
        exposure.symbol,
        exposure,
        h_star,
        h_act,
        actionable,
        residual,
        regime,
        policy_kind=policy_kind,
        gamma_flag=gamma_flag,
    )
    reason = (
        f"h_star={h_star:.2f}; drift={drift:.3f}; breached={breached}; "
        f"regime={regime.value}; gamma_flag={gamma_flag}"
    )

    return HedgeReview(
        symbol=exposure.symbol,
        as_of=exposure.as_of,
        regime=regime,
        policy_kind=policy_kind,
        h_star=h_star,
        h_actual=h_act,
        book_lots=exposure.book_lots,
        hedge_lots=exposure.hedge_lots,
        drift_lots=drift,
        drift_lots_actionable=actionable,
        residual_lots_after_action=residual,
        band_breached=breached,
        urgency=urgency if suppress is None else "none",
        reason=reason,
        copy_review=copy if suppress is None else "",
        suppress_reason=suppress,
        net_gamma=exposure.net_gamma,
        gamma_flag=gamma_flag,
    )


def _suppressed(
    exposure: HedgeExposure,
    symbol_policy: SymbolPolicy,
    policy: HedgeRebalancePolicy,
    regime: RegimeLabel,
    policy_kind: PolicyKind,
    why: str,
) -> HedgeReview:
    h_star = effective_target(symbol_policy.h_star, regime, policy)
    return HedgeReview(
        symbol=exposure.symbol,
        as_of=exposure.as_of,
        regime=regime,
        policy_kind=policy_kind,
        h_star=h_star,
        h_actual=exposure.hedge_ratio,
        book_lots=exposure.book_lots,
        hedge_lots=exposure.hedge_lots,
        drift_lots=0.0,
        drift_lots_actionable=0.0,
        residual_lots_after_action=0.0,
        band_breached=False,
        urgency="none",
        reason=why,
        copy_review="",
        suppress_reason=why,
        net_gamma=exposure.net_gamma,
        gamma_flag=False,
    )


def evaluate_book(
    exposures: Iterable[HedgeExposure],
    policy: HedgeRebalancePolicy,
    regime: RegimeLabel,
    *,
    policy_kind: PolicyKind = PolicyKind.INVENTORY_HEDGE,
    meta_by_symbol: Optional[dict[str, dict]] = None,
) -> list[HedgeReview]:
    by_sym = {p.symbol: p for p in policy.symbols}
    meta_by_symbol = meta_by_symbol or {}
    out: list[HedgeReview] = []
    for exp in exposures:
        sp = by_sym.get(exp.symbol)
        if sp is None:
            continue
        m = meta_by_symbol.get(exp.symbol, {})
        out.append(
            evaluate_symbol(
                exp,
                sp,
                policy,
                regime,
                policy_kind=policy_kind,
                days_since_last_prompt=m.get("days_since_last_prompt"),
                days_to_roll=m.get("days_to_roll"),
                force=bool(m.get("force", False)),
            )
        )
    return out
