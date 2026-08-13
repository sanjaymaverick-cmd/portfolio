from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from meridian.config import RegimeCfg

LABELS = ("Calm", "Elevated", "Stress")
_RANK = {"Calm": 0, "Elevated": 1, "Stress": 2}


@dataclass
class RegimeInputs:
    as_of: datetime
    vix: float | None
    nifty_close: float | None
    nifty_vs_sma50: float | None
    ewma_vol_ann: float | None
    kalman_trend: float | None
    kalman_trend_z: float | None
    kalman_trend_ann_pct: float | None
    fii_net_5d: float | None = None
    vix_source: str = "missing"
    notes: list[str] = field(default_factory=list)

    def reason_bits(self) -> list[str]:
        bits: list[str] = []
        if self.vix is not None:
            src = "" if self.vix_source == "india_vix" else f" ({self.vix_source})"
            bits.append(f"VIX {self.vix:.1f}{src}")
        if self.ewma_vol_ann is not None:
            bits.append(f"EWMA vol {self.ewma_vol_ann * 100:.1f}%")
        if self.kalman_trend_z is not None:
            bits.append(f"trend z {self.kalman_trend_z:+.2f}")
        if self.nifty_vs_sma50 is not None:
            bits.append(f"Nifty vs SMA50 {self.nifty_vs_sma50:+.1f}%")
        if self.fii_net_5d is not None:
            bits.append(f"FII 5d {self.fii_net_5d:+.0f}")
        bits.extend(self.notes)
        return bits


@dataclass
class RegimeDecision:
    label: str
    previous: str | None
    candidate: str
    soft: dict[str, float]
    reason: str
    held_days: int
    pending: str | None
    pending_days: int


def raw_candidate(inputs: RegimeInputs, cfg: RegimeCfg) -> str:
    rank = 0
    vix_rank = _vix_rank(inputs.vix, cfg)
    if vix_rank is not None:
        rank = max(rank, vix_rank)
    vol = inputs.ewma_vol_ann
    if vol is not None:
        if vol >= cfg.ewma_vol_stress:
            rank = max(rank, 2)
        elif vol >= cfg.ewma_vol_elevated:
            rank = max(rank, 1)
    z = inputs.kalman_trend_z
    if z is not None:
        if z <= cfg.trend_z_risk_off:
            rank = min(2, rank + 1)
        elif z >= cfg.trend_z_risk_on:
            rank = max(0, rank - 1)
    return LABELS[rank]


def apply_hysteresis(current: str, candidate: str, inputs: RegimeInputs, cfg: RegimeCfg) -> str:
    vix = inputs.vix
    vol = inputs.ewma_vol_ann
    if current == "Stress":
        vix_ok = vix is None or vix <= cfg.vix_stress_exit
        vol_ok = vol is None or vol < cfg.ewma_vol_stress
        if candidate != "Stress" and vix_ok and vol_ok:
            return candidate if candidate != "Stress" else "Elevated"
        return "Stress"
    if current == "Elevated":
        if candidate == "Stress":
            return "Stress"
        if candidate == "Calm":
            if vix is not None and vix <= cfg.vix_elevated_exit_to_calm:
                return "Calm"
            return "Elevated"
        return "Elevated"
    return candidate


def confirm_switch(
    current: str,
    proposed: str,
    *,
    held_days: int,
    pending: str | None,
    pending_days: int,
    cfg: RegimeCfg,
) -> tuple[str, str | None, int]:
    if proposed == current:
        return current, None, 0
    if held_days < cfg.min_hold_days:
        return current, proposed, 1
    if pending != proposed:
        return current, proposed, 1
    next_pending = pending_days + 1
    if next_pending >= cfg.confirmation_days:
        return proposed, None, 0
    return current, proposed, next_pending


def soft_weights(inputs: RegimeInputs, cfg: RegimeCfg) -> dict[str, float]:
    parts: list[float] = []
    if inputs.vix is not None:
        parts.append(_unit(inputs.vix, cfg.vix_calm_max, cfg.vix_elevated_max))
    if inputs.ewma_vol_ann is not None:
        parts.append(_unit(inputs.ewma_vol_ann, cfg.ewma_vol_elevated, cfg.ewma_vol_stress))
    if inputs.kalman_trend_z is not None:
        # negative z → risk-off
        parts.append(_unit(-inputs.kalman_trend_z, -cfg.trend_z_risk_on, -cfg.trend_z_risk_off))
    heat = sum(parts) / len(parts) if parts else 0.35
    stress = max(0.0, heat - 0.55) / 0.45
    calm = max(0.0, 0.45 - heat) / 0.45
    elevated = max(0.0, 1.0 - calm - stress)
    total = calm + elevated + stress or 1.0
    return {
        "Calm": round(calm / total, 4),
        "Elevated": round(elevated / total, 4),
        "Stress": round(stress / total, 4),
    }


def decide(
    inputs: RegimeInputs,
    cfg: RegimeCfg,
    *,
    current: str | None,
    since: date | None,
    pending: str | None,
    pending_days: int,
) -> RegimeDecision:
    as_of = inputs.as_of.date() if hasattr(inputs.as_of, "date") else inputs.as_of
    held = 0
    if current and since:
        held = max(0, (as_of - since).days)
    start = current or "Calm"
    candidate = raw_candidate(inputs, cfg)
    proposed = apply_hysteresis(start, candidate, inputs, cfg)
    label, next_pending, next_days = confirm_switch(
        start,
        proposed,
        held_days=held,
        pending=pending,
        pending_days=pending_days,
        cfg=cfg,
    )
    weights = soft_weights(inputs, cfg)
    bits = inputs.reason_bits()
    bits.append(f"{start}→{label}" if label != start else f"hold {label}")
    return RegimeDecision(
        label=label,
        previous=current,
        candidate=candidate,
        soft=weights,
        reason=" · ".join(bits),
        held_days=held if label == start else 0,
        pending=next_pending,
        pending_days=next_days,
    )


def _vix_rank(vix: float | None, cfg: RegimeCfg) -> int | None:
    if vix is None:
        return None
    if vix >= cfg.vix_elevated_max:
        return 2
    if vix >= cfg.vix_calm_max:
        return 1
    return 0


def _unit(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))
