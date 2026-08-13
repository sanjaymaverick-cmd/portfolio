from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from meridian.config import ScoringCfg, Settings, get_settings
from meridian.storage.fundamentals import FactorRepo
from meridian.storage.regime import RegimeRepo
from meridian.storage.schema import FactorScore, RegimeSnapshot

FACTORS = ("quality", "valuation", "technical", "ownership", "sentiment")

DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "Calm": {
        "quality": 0.28,
        "valuation": 0.22,
        "technical": 0.18,
        "ownership": 0.18,
        "sentiment": 0.14,
    },
    "Elevated": {
        "quality": 0.26,
        "valuation": 0.16,
        "technical": 0.22,
        "ownership": 0.22,
        "sentiment": 0.14,
    },
    "Stress": {
        "quality": 0.24,
        "valuation": 0.10,
        "technical": 0.26,
        "ownership": 0.26,
        "sentiment": 0.14,
    },
}

DEFAULT_GATES: dict[str, dict[str, float]] = {
    "Calm": {"strong_buy": 8.0, "buy": 6.8, "hold": 5.0, "reduce": 3.8},
    "Elevated": {"strong_buy": 8.3, "buy": 7.1, "hold": 5.2, "reduce": 4.0},
    "Stress": {"strong_buy": 8.6, "buy": 7.4, "hold": 5.5, "reduce": 4.2},
}


def blend_weights(regime: RegimeSnapshot | None, cfg: ScoringCfg | None = None) -> dict[str, Decimal]:
    table = (cfg.weights if cfg and cfg.weights else DEFAULT_WEIGHTS)
    if regime is None:
        raw = table.get("Calm", DEFAULT_WEIGHTS["Calm"])
        return {key: Decimal(str(raw[key])) for key in FACTORS if key in raw}
    soft = {
        "Calm": float(regime.soft_calm or 0),
        "Elevated": float(regime.soft_elevated or 0),
        "Stress": float(regime.soft_stress or 0),
    }
    if sum(soft.values()) <= 0:
        soft[regime.label or "Calm"] = 1.0
    blended: dict[str, Decimal] = {}
    for factor in FACTORS:
        total = 0.0
        for label, mass in soft.items():
            total += mass * table.get(label, DEFAULT_WEIGHTS["Calm"]).get(factor, 0.0)
        blended[factor] = Decimal(str(round(total, 4)))
    return blended


def composite_score(row: FactorScore, weights: dict[str, Decimal]) -> Decimal | None:
    total = Decimal("0")
    mass = Decimal("0")
    for factor, weight in weights.items():
        value = getattr(row, factor, None)
        if value is None:
            continue
        total += Decimal(str(value)) * weight
        mass += weight
    if mass == 0:
        return None
    return (total / mass).quantize(Decimal("0.01"))


def map_action(score: Decimal | None, regime: RegimeSnapshot | None, cfg: ScoringCfg | None = None) -> str:
    if score is None:
        return "—"
    label = regime.label if regime else "Calm"
    gates = (cfg.actions if cfg and cfg.actions else DEFAULT_GATES).get(label, DEFAULT_GATES["Calm"])
    value = float(score)
    if value >= gates["strong_buy"]:
        return "Strong Buy"
    if value >= gates["buy"]:
        return "Buy"
    if value >= gates["hold"]:
        return "Hold"
    if value >= gates["reduce"]:
        return "Reduce"
    return "Sell"


def confidence(row: FactorScore, regime: RegimeSnapshot | None) -> Decimal | None:
    values = [float(getattr(row, name)) for name in FACTORS if getattr(row, name) is not None]
    if len(values) < 2:
        return Decimal("0.40")
    mean = sum(values) / len(values)
    var = sum((item - mean) ** 2 for item in values) / (len(values) - 1)
    spread = var ** 0.5
    base = max(0.25, min(0.92, 0.82 - spread / 8.0))
    if regime is not None:
        peak = max(float(regime.soft_calm or 0), float(regime.soft_elevated or 0), float(regime.soft_stress or 0))
        base = min(0.95, base + 0.08 * peak)
    return Decimal(str(round(base, 2)))


class CompositeService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.factors = FactorRepo(session)
        self.regimes = RegimeRepo(session)

    def rescore_ownership_sentiment(self, symbol: str | None = None) -> int:
        from meridian.scoring.ownership import score_ownership
        from meridian.scoring.sentiment import score_sentiment
        from meridian.storage.fundamentals import FundamentalRepo

        funds = FundamentalRepo(self.session)
        rows = [funds.get(symbol)] if symbol else funds.list()
        written = 0
        for fund in rows:
            if fund is None:
                continue
            snap = funds.to_snap(fund)
            ownership, o_parts = score_ownership(snap)
            sentiment, s_parts = score_sentiment(snap)
            self.factors.patch(
                fund.symbol,
                ownership=ownership,
                sentiment=sentiment,
                ownership_detail=_dump_parts(o_parts),
                sentiment_detail=_dump_parts(s_parts),
            )
            written += 1
        return written

    def recompute(self, symbol: str | None = None) -> int:
        regime = self.regimes.latest()
        weights = blend_weights(regime, self.settings.scoring)
        if symbol:
            rows = [self.factors.get(symbol)]
        else:
            rows = list(self.factors.map_for([]).values()) if False else _all_factors(self.factors)
        written = 0
        for row in rows:
            if row is None:
                continue
            score = composite_score(row, weights)
            action = map_action(score, regime, self.settings.scoring)
            self.factors.patch(
                row.symbol,
                composite=score,
                action=action,
                confidence=confidence(row, regime),
            )
            written += 1
        from meridian.recommendations.service import ExplainService

        ExplainService(self.session, self.settings).explain_all(symbol)
        return written


def _dump_parts(parts: dict[str, Decimal | None]) -> str:
    import json

    return json.dumps({key: None if value is None else float(value) for key, value in parts.items()})


def _all_factors(repo: FactorRepo) -> list[FactorScore]:
    from sqlalchemy import select

    return list(repo.session.scalars(select(FactorScore)))


def brief_reason(row: FactorScore, action: str, regime: str | None) -> str:
    parts = []
    for name in FACTORS:
        value = getattr(row, name, None)
        if value is not None:
            parts.append((name, float(value)))
    if not parts:
        return "Insufficient factors for an action."
    parts.sort(key=lambda item: item[1], reverse=True)
    high = ", ".join(f"{n} {v:.1f}" for n, v in parts[:2])
    low = ", ".join(f"{n} {v:.1f}" for n, v in parts[-2:] if parts[-1][1] < 6)
    desk = f" under {regime}" if regime else ""
    tail = f" Constrained by {low}." if low else ""
    return f"{action}{desk}. Supported by {high}.{tail}"
