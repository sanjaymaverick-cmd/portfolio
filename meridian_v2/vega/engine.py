"""Pure vega-defense engine — no broker.

Normative design: docs/v2/VEGA_HEDGE_SKETCH.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from meridian_v2.domain.enums import PolicyKind


@dataclass(frozen=True)
class OptionGreekLeg:
    leg_id: str
    symbol: str
    contract_label: str
    lots: float
    multiplier: float
    mark_inr: float
    delta: float
    gamma: float
    vega_per_lot: float
    theta_per_lot: float = 0.0
    iv: Optional[float] = None
    as_of: Optional[date] = None

    @property
    def vega(self) -> float:
        return self.lots * self.vega_per_lot

    @property
    def effective_delta_lots(self) -> float:
        return self.lots * self.delta

    @property
    def gamma_lots(self) -> float:
        return self.lots * self.gamma


@dataclass(frozen=True)
class VegaExposure:
    symbol: str
    as_of: date
    net_vega: float
    net_delta_lots: float
    net_gamma: float
    leg_count: int
    iv_ref: Optional[float] = None


@dataclass(frozen=True)
class VegaPolicy:
    symbol: str
    vega_limit: float
    warn_utilization: float = 0.80
    nu_star: float = 0.0
    enabled: bool = True
    hedge_vega_per_lot: Optional[float] = None
    hedge_delta: float = 0.5
    lot_step: float = 1.0


@dataclass(frozen=True)
class VegaReview:
    symbol: str
    as_of: date
    policy_kind: PolicyKind
    net_vega: float
    vega_limit: float
    utilization: float
    over_limit: bool
    nu_star: float
    vega_drift: float
    opt_lots_raw: float
    opt_lots_actionable: float
    residual_vega: float
    futures_delta_lots: float
    urgency: str
    reason: str
    copy_review: str
    suppress_reason: Optional[str] = None


def aggregate_vega(
    symbol: str, legs: Sequence[OptionGreekLeg], as_of: date
) -> VegaExposure:
    use = [x for x in legs if x.symbol == symbol]
    ivs = [x.iv for x in use if x.iv is not None]
    return VegaExposure(
        symbol=symbol,
        as_of=as_of,
        net_vega=sum(x.vega for x in use),
        net_delta_lots=sum(x.effective_delta_lots for x in use),
        net_gamma=sum(x.gamma_lots for x in use),
        leg_count=len(use),
        iv_ref=(sum(ivs) / len(ivs)) if ivs else None,
    )


def utilization(net_vega: float, limit: float) -> float:
    if limit <= 0:
        return 0.0
    return abs(net_vega) / limit


def snap_lots(raw: float, lot_step: float) -> float:
    if lot_step <= 0:
        return raw
    return math.copysign(math.floor(abs(raw) / lot_step + 1e-12) * lot_step, raw)


def option_lots_to_hit_vega_target(
    net_vega: float, nu_star: float, hedge_vega_per_lot: float
) -> float:
    if abs(hedge_vega_per_lot) < 1e-12:
        return 0.0
    return (nu_star - net_vega) / hedge_vega_per_lot


def futures_lots_to_flatten_delta(
    net_delta_lots: float, option_lots: float, hedge_delta: float
) -> float:
    return -(net_delta_lots + option_lots * hedge_delta)


def build_vega_copy(
    symbol: str,
    exp: VegaExposure,
    pol: VegaPolicy,
    opt_q: float,
    fut_q: float,
    util: float,
) -> str:
    side = "long" if exp.net_vega > 0 else "short" if exp.net_vega < 0 else "flat"
    return (
        f"VEGA REVIEW — not an order. [{PolicyKind.VEGA_DEFENSE.value}] {symbol}: "
        f"net vega {exp.net_vega:,.0f} ₹/vol-pt ({side}), limit {pol.vega_limit:,.0f}, "
        f"utilization {util:.0%}. Model option hedge {opt_q:+.1f} lots toward target "
        f"{pol.nu_star:,.0f}; then futures delta clean-up {fut_q:+.1f} lots. "
        f"Review reducing vol exposure, adjusting the option leg, or accepting the mark risk?"
    )


def build_vega_warn_copy(
    symbol: str,
    exp: VegaExposure,
    pol: VegaPolicy,
    util: float,
) -> str:
    """Heads-up copy for a warn-level utilization that is not over the limit.

    No trade is sized here (per the sketch, a soft warn is passive / no-trade),
    so the copy states the situation without proposing a +0.0-lot hedge.
    """
    side = "long" if exp.net_vega > 0 else "short" if exp.net_vega < 0 else "flat"
    return (
        f"VEGA REVIEW — not an order. [{PolicyKind.VEGA_DEFENSE.value}] {symbol}: "
        f"net vega {exp.net_vega:,.0f} ₹/vol-pt ({side}), limit {pol.vega_limit:,.0f}, "
        f"utilization {util:.0%} — approaching the vega limit but still within it. "
        f"No hedge sized. Review trimming vol exposure or accepting the mark risk?"
    )


def evaluate_vega(
    exp: VegaExposure,
    pol: VegaPolicy,
    *,
    hedge_vega_per_lot: float,
    hedge_delta: float | None = None,
    regime_stress: bool = False,
    force: bool = False,
) -> VegaReview:
    if not pol.enabled:
        return VegaReview(
            symbol=exp.symbol,
            as_of=exp.as_of,
            policy_kind=PolicyKind.VEGA_DEFENSE,
            net_vega=exp.net_vega,
            vega_limit=pol.vega_limit,
            utilization=0.0,
            over_limit=False,
            nu_star=pol.nu_star,
            vega_drift=0.0,
            opt_lots_raw=0.0,
            opt_lots_actionable=0.0,
            residual_vega=exp.net_vega,
            futures_delta_lots=0.0,
            urgency="none",
            reason="disabled",
            copy_review="",
            suppress_reason="disabled",
        )

    hd = pol.hedge_delta if hedge_delta is None else hedge_delta
    hvp = (
        pol.hedge_vega_per_lot
        if pol.hedge_vega_per_lot is not None
        else hedge_vega_per_lot
    )
    util = utilization(exp.net_vega, pol.vega_limit)
    over = abs(exp.net_vega) > pol.vega_limit + 1e-6
    warn = util >= pol.warn_utilization
    target = pol.nu_star
    need_trade = over or force

    if not need_trade and not warn:
        return VegaReview(
            symbol=exp.symbol,
            as_of=exp.as_of,
            policy_kind=PolicyKind.VEGA_DEFENSE,
            net_vega=exp.net_vega,
            vega_limit=pol.vega_limit,
            utilization=util,
            over_limit=False,
            nu_star=target,
            vega_drift=exp.net_vega - target,
            opt_lots_raw=0.0,
            opt_lots_actionable=0.0,
            residual_vega=exp.net_vega,
            futures_delta_lots=0.0,
            urgency="none",
            reason="within_limit",
            copy_review="",
            suppress_reason=None,
        )

    raw = (
        option_lots_to_hit_vega_target(exp.net_vega, target, hvp) if need_trade else 0.0
    )
    actionable = snap_lots(raw, pol.lot_step)
    residual = exp.net_vega + actionable * hvp
    fut = (
        futures_lots_to_flatten_delta(exp.net_delta_lots, actionable, hd)
        if actionable
        else 0.0
    )
    fut = snap_lots(fut, pol.lot_step)

    urgency = "none"
    if over or warn:
        urgency = "elevated" if (over and regime_stress) else "review"

    if urgency == "none":
        copy = ""
    elif need_trade:
        copy = build_vega_copy(exp.symbol, exp, pol, actionable, fut, util)
    else:
        # Warn-level only (not over, not forced): no trade was sized, so use
        # the heads-up copy instead of one advising a +0.0-lot hedge.
        copy = build_vega_warn_copy(exp.symbol, exp, pol, util)

    return VegaReview(
        symbol=exp.symbol,
        as_of=exp.as_of,
        policy_kind=PolicyKind.VEGA_DEFENSE,
        net_vega=exp.net_vega,
        vega_limit=pol.vega_limit,
        utilization=util,
        over_limit=over,
        nu_star=target,
        vega_drift=exp.net_vega - target,
        opt_lots_raw=raw,
        opt_lots_actionable=actionable,
        residual_vega=residual,
        futures_delta_lots=fut,
        urgency=urgency,
        reason=f"util={util:.2f}; over={over}; stress={regime_stress}",
        copy_review=copy,
        suppress_reason=None,
    )
