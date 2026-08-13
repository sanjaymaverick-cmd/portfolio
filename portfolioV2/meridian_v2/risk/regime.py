"""Desk regime from tape — VIX/Kalman *concepts*, not a v1 import."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.domain.models import RegimeLabel
from meridian_v2.storage.schema import FxMark, PriceCache, RegimeState


def infer_regime(*, usdinr_move_pct: float | None, gold_vs_sma: float | None) -> tuple[str, str]:
    stress_fx = usdinr_move_pct is not None and abs(usdinr_move_pct) >= 1.2
    stress_cmd = gold_vs_sma is not None and gold_vs_sma <= -0.03
    calm_fx = usdinr_move_pct is not None and abs(usdinr_move_pct) < 0.35
    if stress_fx or stress_cmd:
        return RegimeLabel.STRESS.value, (
            f"Stress sensors: USDINR move {usdinr_move_pct or 0:+.2f}%, "
            f"GOLD vs SMA {gold_vs_sma or 0:+.2%}"
        )
    if calm_fx and (gold_vs_sma is None or gold_vs_sma >= 0):
        return RegimeLabel.CALM.value, "Calm sensors: tight USDINR and GOLD at/above SMA"
    return RegimeLabel.ELEVATED.value, "Elevated sensors: mixed FX / commodity tape"


class RegimeService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def refresh(self) -> RegimeState:
        fx = self.session.scalar(select(FxMark).where(FxMark.pair == "USDINR"))
        gold = self.session.scalar(
            select(PriceCache).where(PriceCache.symbol == "GOLD", PriceCache.contract_label == "CONTINUOUS")
        )
        move = None
        if fx and fx.last and fx.prev_close:
            move = (fx.last - fx.prev_close) / fx.prev_close * 100
        vs_sma = None
        if gold and gold.last and gold.sma20:
            vs_sma = (gold.last - gold.sma20) / gold.sma20
        label, reason = infer_regime(usdinr_move_pct=move, gold_vs_sma=vs_sma)
        now = datetime.now(UTC).replace(tzinfo=None)
        row = self.session.scalar(select(RegimeState).order_by(RegimeState.as_of.desc()))
        if row is None:
            row = RegimeState(label=label, reason=reason, as_of=now)
            self.session.add(row)
        else:
            row.label = label
            row.reason = reason
            row.as_of = now
        self.session.flush()
        return row
