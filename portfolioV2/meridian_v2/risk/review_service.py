"""Assemble a full review + chart DTO from the desk book. No orders."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.config import get_settings
from meridian_v2.domain.reviews import PlainReview, ReviewScenario, compose_review
from meridian_v2.domain.templates import catalog_payload
from meridian_v2.hedge.engine import RegimeLabel
from meridian_v2.mcx.roll import days_to_roll
from meridian_v2.mcx.service import McxService
from meridian_v2.risk.gamma_scalp import explain_scalp
from meridian_v2.risk.greeks_book import GreekSnapshot, snapshot_from_legs
from meridian_v2.risk.vega_strategies import HedgeUnit, VegaAction, plan_vega_actions
from meridian_v2.storage.schema import OptionLegRow, PriceCache
from meridian_v2.vega.engine import OptionGreekLeg, VegaPolicy, utilization


def _legs(session: Session, symbol: str) -> list[OptionGreekLeg]:
    rows = list(session.scalars(select(OptionLegRow).where(OptionLegRow.symbol == symbol)))
    return [
        OptionGreekLeg(
            leg_id=row.leg_id,
            symbol=row.symbol,
            contract_label=row.contract_label,
            lots=row.lots,
            multiplier=row.multiplier,
            mark_inr=row.mark_inr,
            delta=row.delta,
            gamma=row.gamma,
            vega_per_lot=row.vega_per_lot,
            theta_per_lot=row.theta_per_lot or 0.0,
            iv=row.iv,
            stale=bool(row.stale),
        )
        for row in rows
    ]


def _policy(symbol: str) -> VegaPolicy:
    cfg = get_settings().hedge.vega.get(symbol)
    if cfg is None:
        return VegaPolicy(symbol, 200_000, hedge_vega_per_lot=55_000, hedge_delta=0.48)
    return VegaPolicy(
        symbol,
        cfg.vega_limit,
        warn_utilization=cfg.warn_utilization,
        nu_star=cfg.nu_star,
        enabled=cfg.enabled,
        hedge_vega_per_lot=cfg.hedge_vega_per_lot,
        hedge_delta=cfg.hedge_delta,
        lot_step=cfg.lot_step,
    )


def _unit(policy: VegaPolicy, legs: list[OptionGreekLeg]) -> HedgeUnit:
    if legs:
        sample = max(legs, key=lambda leg: abs(leg.vega_per_lot))
        return HedgeUnit(
            vega=policy.hedge_vega_per_lot or sample.vega_per_lot or 55_000,
            delta=policy.hedge_delta,
            gamma=sample.gamma,
            theta=sample.theta_per_lot,
        )
    return HedgeUnit(
        vega=policy.hedge_vega_per_lot or 55_000,
        delta=policy.hedge_delta,
        gamma=0.02,
        theta=-800.0,
    )


def build_desk_review(
    session: Session,
    symbol: str,
    *,
    regime: RegimeLabel = RegimeLabel.ELEVATED,
    as_of: date | None = None,
) -> dict[str, Any]:
    day = as_of or date.today()
    legs = _legs(session, symbol)
    snap = snapshot_from_legs(symbol, legs, day)
    policy = _policy(symbol)
    unit = _unit(policy, legs)
    specs = {spec.symbol_key: spec for spec in McxService(session).specs()}
    dte = days_to_roll(day, specs[symbol].roll_date) if symbol in specs else None
    peers = [
        (row.symbol, row.lots * row.vega_per_lot)
        for row in session.scalars(select(OptionLegRow))
    ]
    actions = plan_vega_actions(
        snap, policy, unit, regime=regime, days_to_expiry=dte, peer_vega=peers
    )
    model_lots = next((a.opt_lots for a in actions if a.key == "limit_cap"), 0.0)
    review = compose_review(snap, vega_limit=policy.vega_limit, model_lots=model_lots)
    scalp = explain_scalp(snap, lot_step=policy.lot_step)
    combined = compose_review(
        snap,
        scenario=ReviewScenario.COMBINED,
        vega_limit=policy.vega_limit,
        model_lots=model_lots,
    )
    scalp_review = compose_review(
        snap,
        scenario=ReviewScenario.GAMMA_SCALP,
        model_lots=scalp.suggested_futures_lots,
    )
    return {
        "symbol": symbol,
        "as_of": day.isoformat(),
        "stale": snap.stale,
        "greeks": {
            "delta_lots": snap.delta_lots,
            "gamma": snap.gamma,
            "gamma_sign": snap.gamma_sign,
            "vega": snap.vega,
            "theta": snap.theta,
            "utilization": utilization(snap.vega, policy.vega_limit),
            "vega_limit": policy.vega_limit,
            "daily_pnl": snap.daily_pnl,
            "gamma_scalp_pnl": snap.gamma_scalp_pnl,
            "move_pct": snap.move_pct,
            "scalp_helps": snap.scalp_helps,
            "net_after_move_day": scalp.net_after_move_day,
            "move_covers_theta": scalp.move_covers_theta,
        },
        "review": review.as_dict(),
        "combined": combined.as_dict(),
        "gamma_scalp": scalp.as_dict(),
        "gamma_scalp_review": scalp_review.as_dict(),
        "actions": [_action_dict(item) for item in actions],
        "catalog": catalog_payload(),
    }


def _action_dict(action: VegaAction) -> dict[str, Any]:
    return {
        "key": action.key,
        "title": action.title,
        "enabled": action.enabled,
        "opt_lots": action.opt_lots,
        "effects": {
            "delta": action.d_delta,
            "gamma": action.d_gamma,
            "vega": action.d_vega,
            "theta": action.d_theta,
        },
        "after_vega": action.after_vega,
        "after_util": action.after_util,
        "note": action.note,
    }


def mark_row(session: Session, symbol: str) -> PriceCache | None:
    return session.scalar(
        select(PriceCache).where(
            PriceCache.symbol == symbol, PriceCache.contract_label == "CONTINUOUS"
        )
    )


def review_from_snapshot(snap: GreekSnapshot, **kwargs: Any) -> PlainReview:
    return compose_review(snap, **kwargs)
