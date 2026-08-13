from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta
from time import sleep

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.config import Settings, get_settings
from meridian_v2.domain.copy import fx_review_copy
from meridian_v2.domain.models import PolicyKind, SignalStatus
from meridian_v2.hedge.engine import (
    AssetClass,
    BookLeg,
    HedgeLeg,
    HedgeRebalancePolicy,
    RebalanceBand,
    RegimeLabel,
    SymbolPolicy,
    aggregate_exposure,
    evaluate_book,
)
from meridian_v2.hedge.vol_harvest import evaluate_vol_harvest
from meridian_v2.mcx.roll import days_to_roll
from meridian_v2.mcx.service import McxService
from meridian_v2.scoring.service import ScoringService
from meridian_v2.signals.engines import evaluate_signals
from meridian_v2.signals.service import SignalService
from meridian_v2.storage.db import get_session
from meridian_v2.storage.schema import (
    BookLegRow,
    Cooldown,
    FxMark,
    HedgeLegRow,
    McxContract,
    OptionLegRow,
    PriceCache,
    RegimeState,
    WatchItem,
)
from meridian_v2.vega.engine import OptionGreekLeg, VegaPolicy, aggregate_vega, evaluate_vega


def current_regime(session: Session, settings: Settings) -> RegimeLabel:
    row = session.scalar(select(RegimeState).order_by(RegimeState.as_of.desc()))
    label = row.label if row else settings.regime.default_label
    try:
        return RegimeLabel(label)
    except ValueError:
        return RegimeLabel.ELEVATED


def _cooldown_days(session: Session, policy_kind: str, symbol: str) -> int | None:
    row = session.scalar(
        select(Cooldown).where(Cooldown.policy_kind == policy_kind, Cooldown.symbol == symbol)
    )
    if row is None:
        return None
    delta = datetime.now(UTC).replace(tzinfo=None) - row.last_prompt_at
    return max(0, delta.days)


def _snoozed(session: Session, policy_kind: str, symbol: str) -> bool:
    row = session.scalar(
        select(Cooldown).where(Cooldown.policy_kind == policy_kind, Cooldown.symbol == symbol)
    )
    if row is None or row.snooze_until is None:
        return False
    return row.snooze_until > datetime.now(UTC).replace(tzinfo=None)


def _touch_cooldown(session: Session, policy_kind: str, symbol: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    row = session.scalar(
        select(Cooldown).where(Cooldown.policy_kind == policy_kind, Cooldown.symbol == symbol)
    )
    if row is None:
        session.add(Cooldown(policy_kind=policy_kind, symbol=symbol, last_prompt_at=now))
    else:
        row.last_prompt_at = now


def _payload(obj: object) -> dict:
    if is_dataclass(obj):
        data = asdict(obj)
        for key, value in list(data.items()):
            if isinstance(value, date):
                data[key] = value.isoformat()
        return data
    return {}


class AlertWorker:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.signals = SignalService(session)

    def run_once(self, *, force: bool = False, poll_marks: bool = False) -> dict[str, int]:
        if not self.settings.modules.alerts and not force:
            return {"opened": 0, "marked": 0}
        marked = 0
        if poll_marks:
            from meridian_v2.data_providers.service import PriceProvider, apply_cached_marks

            result = PriceProvider(self.session).refresh()
            marked = int(result.get("marked") or 0)
            apply_cached_marks(self.session)
        from meridian_v2.risk.regime import RegimeService

        RegimeService(self.session).refresh()
        ScoringService(self.session).rescore(current_regime(self.session, self.settings).value)
        opened = 0
        if self.settings.modules.inventory_hedge:
            opened += self._inventory(force=force)
        if self.settings.modules.vol_harvest:
            opened += self._vol_harvest(force=force)
        if self.settings.modules.vega_defense:
            opened += self._vega(force=force)
        if self.settings.modules.signals:
            opened += self._signals()
        if self.settings.modules.fx:
            opened += self._fx()
        opened += self._policies()
        return {"opened": opened, "marked": marked}

    def _inventory(self, *, force: bool) -> int:
        regime = current_regime(self.session, self.settings)
        book = list(self.session.scalars(select(BookLegRow)))
        hedges = list(self.session.scalars(select(HedgeLegRow)))
        if not book and not hedges:
            return 0
        symbols = sorted({row.symbol for row in book} | {row.symbol for row in hedges})
        book_legs = [
            BookLeg(
                leg_id=r.leg_id,
                symbol=r.symbol,
                asset_class=AssetClass(r.asset_class),
                lots=r.lots,
                multiplier=r.multiplier,
                mark_inr=r.mark_inr,
                contract_label=r.contract_label,
                delta=r.delta,
                gamma=r.gamma,
                as_of=r.as_of,
            )
            for r in book
        ]
        hedge_legs = [
            HedgeLeg(
                leg_id=r.leg_id,
                symbol=r.symbol,
                asset_class=AssetClass(r.asset_class),
                lots=r.lots,
                multiplier=r.multiplier,
                mark_inr=r.mark_inr,
                contract_label=r.contract_label,
                delta=r.delta,
                gamma=r.gamma,
                as_of=r.as_of,
            )
            for r in hedges
        ]
        today = date.today()
        exposures = [
            aggregate_exposure(sym, AssetClass.COMMODITY, book_legs, hedge_legs, today)
            for sym in symbols
        ]
        policies = []
        for sym, cfg in self.settings.hedge.inventory.items():
            policies.append(
                SymbolPolicy(
                    symbol=sym,
                    h_star=cfg.h_star,
                    band=RebalanceBand(min_lots=cfg.min_lots, ratio_tol=cfg.ratio_tol),
                    lot_step=cfg.lot_step,
                    enabled=cfg.enabled,
                    gamma_warn_abs=cfg.gamma_warn_abs,
                )
            )
        policy = HedgeRebalancePolicy(
            symbols=tuple(policies),
            min_days_between_prompts=self.settings.hedge.min_days_between_prompts,
            roll_blackout_days=self.settings.hedge.roll_blackout_days,
        )
        meta: dict[str, dict] = {}
        for spec in McxService(self.session).specs():
            meta[spec.symbol_key] = {
                "days_to_roll": days_to_roll(today, spec.roll_date),
                "days_since_last_prompt": _cooldown_days(
                    self.session, PolicyKind.INVENTORY_HEDGE.value, spec.symbol_key
                ),
                "force": force,
            }
        opened = 0
        for review in evaluate_book(exposures, policy, regime, meta_by_symbol=meta):
            if review.urgency == "none" or review.suppress_reason:
                continue
            if _snoozed(self.session, PolicyKind.INVENTORY_HEDGE.value, review.symbol):
                continue
            self.signals.enqueue(
                policy_kind=PolicyKind.INVENTORY_HEDGE.value,
                symbol=review.symbol,
                copy_review=review.copy_review,
                reason=review.reason,
                regime=regime.value,
                rule_name="inventory_hedge",
                payload=_payload(review),
            )
            _touch_cooldown(self.session, PolicyKind.INVENTORY_HEDGE.value, review.symbol)
            opened += 1
        return opened

    def _vol_harvest(self, *, force: bool) -> int:
        regime = current_regime(self.session, self.settings)
        options = list(self.session.scalars(select(OptionLegRow)))
        hedges = list(self.session.scalars(select(HedgeLegRow)))
        if not options:
            return 0
        today = date.today()
        opened = 0
        symbols = sorted({row.symbol for row in options})
        for symbol in symbols:
            book_legs = [
                BookLeg(
                    leg_id=r.leg_id,
                    symbol=r.symbol,
                    asset_class=AssetClass.COMMODITY,
                    lots=r.lots,
                    multiplier=r.multiplier,
                    mark_inr=r.mark_inr,
                    contract_label=r.contract_label,
                    delta=r.delta,
                    gamma=r.gamma,
                    as_of=today,
                )
                for r in options
                if r.symbol == symbol
            ]
            hedge_legs = [
                HedgeLeg(
                    leg_id=r.leg_id,
                    symbol=r.symbol,
                    asset_class=AssetClass.COMMODITY,
                    lots=r.lots,
                    multiplier=r.multiplier,
                    mark_inr=r.mark_inr,
                    contract_label=r.contract_label,
                    delta=r.delta,
                    gamma=r.gamma,
                    as_of=r.as_of,
                )
                for r in hedges
                if r.symbol == symbol
            ]
            exposure = aggregate_exposure(symbol, AssetClass.COMMODITY, book_legs, hedge_legs, today)
            review = evaluate_vol_harvest(
                exposure,
                regime=regime,
                min_lots=self.settings.hedge.vol_harvest.min_lots,
                lot_step=self.settings.hedge.vol_harvest.lot_step,
                days_since_last_prompt=_cooldown_days(
                    self.session, PolicyKind.VOL_HARVEST.value, symbol
                ),
                min_days_between_prompts=self.settings.hedge.min_days_between_prompts,
                force=force,
            )
            if review.urgency == "none" or review.suppress_reason:
                continue
            if _snoozed(self.session, PolicyKind.VOL_HARVEST.value, symbol):
                continue
            self.signals.enqueue(
                policy_kind=PolicyKind.VOL_HARVEST.value,
                symbol=symbol,
                copy_review=review.copy_review,
                reason=review.reason,
                regime=regime.value,
                rule_name="vol_harvest",
                payload=_payload(review),
            )
            _touch_cooldown(self.session, PolicyKind.VOL_HARVEST.value, symbol)
            opened += 1
        return opened

    def _vega(self, *, force: bool) -> int:
        regime = current_regime(self.session, self.settings)
        options = list(self.session.scalars(select(OptionLegRow)))
        if not options:
            return 0
        today = date.today()
        opened = 0
        symbols = sorted({row.symbol for row in options})
        for symbol in symbols:
            cfg = self.settings.hedge.vega.get(symbol)
            if cfg is None or not cfg.enabled:
                continue
            legs = [
                OptionGreekLeg(
                    leg_id=r.leg_id,
                    symbol=r.symbol,
                    contract_label=r.contract_label,
                    lots=r.lots,
                    multiplier=r.multiplier,
                    mark_inr=r.mark_inr,
                    delta=r.delta,
                    gamma=r.gamma,
                    vega_per_lot=r.vega_per_lot,
                    theta_per_lot=r.theta_per_lot,
                    iv=r.iv,
                    as_of=today,
                    stale=bool(r.stale),
                )
                for r in options
                if r.symbol == symbol
            ]
            exp = aggregate_vega(symbol, legs, today)
            pol = VegaPolicy(
                symbol=symbol,
                vega_limit=cfg.vega_limit,
                warn_utilization=cfg.warn_utilization,
                nu_star=cfg.nu_star,
                enabled=cfg.enabled,
                hedge_vega_per_lot=cfg.hedge_vega_per_lot,
                hedge_delta=cfg.hedge_delta,
                lot_step=cfg.lot_step,
            )
            review = evaluate_vega(
                exp,
                pol,
                hedge_vega_per_lot=cfg.hedge_vega_per_lot,
                hedge_delta=cfg.hedge_delta,
                regime_stress=regime == RegimeLabel.STRESS,
                force=force,
            )
            if review.urgency == "none":
                continue
            if not force and _snoozed(self.session, PolicyKind.VEGA_DEFENSE.value, symbol):
                continue
            days = _cooldown_days(self.session, PolicyKind.VEGA_DEFENSE.value, symbol)
            if (
                not force
                and days is not None
                and days < self.settings.hedge.min_days_between_prompts
                and not (regime == RegimeLabel.STRESS and review.over_limit)
            ):
                continue
            self.signals.enqueue(
                policy_kind=PolicyKind.VEGA_DEFENSE.value,
                symbol=symbol,
                copy_review=review.copy_review,
                reason=review.reason,
                regime=regime.value,
                rule_name="vega_defense",
                payload=_payload(review),
            )
            _touch_cooldown(self.session, PolicyKind.VEGA_DEFENSE.value, symbol)
            opened += 1
        return opened

    def _signals(self) -> int:
        regime = current_regime(self.session, self.settings)
        active = list(
            self.session.scalars(select(WatchItem).where(WatchItem.status == "active"))
        )
        book_symbols = {r.symbol for r in self.session.scalars(select(BookLegRow))}
        scores = ScoringService(self.session).score_active(regime.value)
        usdinr = self.session.scalar(select(FxMark).where(FxMark.pair == "USDINR"))
        usdinr_move = None
        if usdinr and usdinr.last and usdinr.prev_close:
            usdinr_move = (usdinr.last - usdinr.prev_close) / usdinr.prev_close * 100
        gold = self.session.scalar(
            select(PriceCache).where(PriceCache.symbol == "GOLD", PriceCache.contract_label == "CONTINUOUS")
        )
        commodity_stress = bool(
            gold and gold.last and gold.sma20 and gold.last < gold.sma20 * 0.97
        ) or regime.value == "Stress"
        opened = 0
        for item in active:
            price = self.session.scalar(
                select(PriceCache).where(
                    PriceCache.symbol == item.symbol,
                    PriceCache.contract_label == "CONTINUOUS",
                )
            )
            raws = evaluate_signals(
                symbol=item.symbol,
                asset_class=item.asset_class,
                score=scores.get(item.symbol),
                last=price.last if price else None,
                sma=price.sma20 if price else None,
                sma50=price.sma50 if price else None,
                weekly_last=price.weekly_last if price else None,
                weekly_sma=price.weekly_sma if price else None,
                high20=price.high20 if price else None,
                low20=price.low20 if price else None,
                volume=price.volume if price else None,
                prev_volume=price.prev_volume if price else None,
                regime=regime.value,
                in_book=item.symbol in book_symbols,
                usdinr_move_pct=usdinr_move,
                commodity_stress=commodity_stress,
            )
            for raw in raws:
                status = (
                    SignalStatus.PENDING.value
                    if raw.portfolio_relevant
                    else SignalStatus.LOG_ONLY.value
                )
                self.signals.enqueue(
                    policy_kind=PolicyKind.SIGNAL.value,
                    symbol=raw.symbol,
                    copy_review=raw.reason,
                    reason=raw.reason,
                    regime=regime.value,
                    rule_name=raw.rule_name,
                    strength=raw.strength,
                    payload={"params": raw.params},
                    status=status,
                )
                if status == SignalStatus.PENDING.value:
                    opened += 1
        return opened

    def _fx(self) -> int:
        regime = current_regime(self.session, self.settings)
        threshold = self.settings.fx.move_review_pct
        opened = 0
        has_commodity = self.session.scalar(select(BookLegRow).limit(1)) is not None
        for mark in self.session.scalars(select(FxMark)):
            if mark.last is None or mark.prev_close in (None, 0):
                continue
            move = (mark.last - mark.prev_close) / mark.prev_close * 100
            if abs(move) < threshold:
                continue
            if not has_commodity:
                continue
            why = (
                f"Move size {move:+.2f}% with open commodity book legs — "
                f"exposure may need a hedge review."
            )
            copy = fx_review_copy(pair=mark.pair, move_pct=move, regime=regime.value, why=why)
            self.signals.enqueue(
                policy_kind=PolicyKind.FX_REVIEW.value,
                symbol=mark.pair,
                copy_review=copy,
                reason=why,
                regime=regime.value,
                rule_name="fx_move",
                payload={"move_pct": move},
            )
            opened += 1
        return opened

    def _policies(self) -> int:
        from meridian_v2.alerts.policies import evaluate_policies

        regime = current_regime(self.session, self.settings)
        return evaluate_policies(self.session, regime=regime.value)


def run_once(*, force: bool = False, poll_marks: bool = False) -> dict[str, int]:
    session = get_session()
    try:
        result = AlertWorker(session).run_once(force=force, poll_marks=poll_marks)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_worker(poll_seconds: int | None = None) -> None:
    settings = get_settings()
    interval = poll_seconds if poll_seconds is not None else settings.alerts.poll_seconds
    while True:
        run_once(poll_marks=True)
        sleep(max(5, interval))
