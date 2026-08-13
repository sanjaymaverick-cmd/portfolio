"""Multi-factor scores for *active* watch names only. Concepts from v1, no v1 import."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.domain.models import WatchStatus
from meridian_v2.storage.schema import FactorScore, NewsStub, PriceCache, WatchItem

WEIGHTS = {
    "Calm": {"technical": 0.18, "tape": 0.22, "regime_fit": 0.14, "news": 0.14, "quality": 0.32},
    "Elevated": {"technical": 0.22, "tape": 0.20, "regime_fit": 0.20, "news": 0.14, "quality": 0.24},
    "Stress": {"technical": 0.26, "tape": 0.16, "regime_fit": 0.26, "news": 0.14, "quality": 0.18},
}


def _clip(value: float) -> float:
    return float(max(0.0, min(10.0, value)))


def tape_score(last: float | None, prev: float | None) -> float | None:
    if last is None or prev is None or prev == 0:
        return None
    return _clip(5.0 + ((last - prev) / prev) * 80.0)


def technical_score(last: float | None, sma20: float | None, sma50: float | None) -> float | None:
    if last is None or sma20 is None or sma20 == 0:
        return tape_score(last, sma20)
    vs20 = (last - sma20) / sma20
    vs50 = (last - sma50) / sma50 if sma50 else vs20
    return _clip(5.0 + vs20 * 40.0 + vs50 * 20.0)


def regime_fit_score(regime: str, last: float | None, sma20: float | None) -> float:
    if last is None or sma20 is None or sma20 == 0:
        return 5.0
    above = last >= sma20
    if regime == "Calm":
        return 7.5 if above else 4.5
    if regime == "Stress":
        return 3.5 if above else 6.0
    return 6.0 if above else 4.8


def news_score(tone: float | None) -> float:
    if tone is None:
        return 5.0
    return _clip(5.0 + tone * 5.0)


def quality_stub(asset_class: str) -> float:
    return 6.5 if asset_class == "equity" else 5.5


def map_stance(composite: float | None, regime: str) -> str:
    if composite is None:
        return "wait"
    if regime == "Stress":
        if composite >= 7.4:
            return "consider"
        if composite <= 4.2:
            return "avoid"
        return "wait"
    if composite >= 6.8:
        return "consider"
    if composite <= 3.8:
        return "avoid"
    return "wait"


@dataclass(frozen=True)
class ScoredName:
    symbol: str
    composite: float
    stance: str
    factors: dict[str, float]


class ScoringService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def score_active(self, regime: str = "Elevated") -> dict[str, float]:
        return {row.symbol: row.composite for row in self.rescore(regime) if row.composite is not None}

    def rescore(self, regime: str = "Elevated") -> list[FactorScore]:
        active = list(
            self.session.scalars(select(WatchItem).where(WatchItem.status == WatchStatus.ACTIVE.value))
        )
        weights = WEIGHTS.get(regime, WEIGHTS["Elevated"])
        now = datetime.now(UTC).replace(tzinfo=None)
        written: list[FactorScore] = []
        for item in active:
            price = self.session.scalar(
                select(PriceCache).where(
                    PriceCache.symbol == item.symbol,
                    PriceCache.contract_label == "CONTINUOUS",
                )
            )
            news = self.session.scalar(
                select(NewsStub).where(NewsStub.symbol == item.symbol).order_by(NewsStub.as_of.desc())
            )
            factors = {
                "technical": technical_score(
                    price.last if price else None,
                    price.sma20 if price else None,
                    price.sma50 if price else None,
                ),
                "tape": tape_score(price.last if price else None, price.prev_close if price else None),
                "regime_fit": regime_fit_score(
                    regime, price.last if price else None, price.sma20 if price else None
                ),
                "news": news_score(news.tone if news else None),
                "quality": quality_stub(item.asset_class),
            }
            mass = 0.0
            total = 0.0
            for key, weight in weights.items():
                value = factors.get(key)
                if value is None:
                    continue
                total += value * weight
                mass += weight
            composite = round(total / mass, 2) if mass else None
            stance = map_stance(composite, regime)
            row = self.session.scalar(select(FactorScore).where(FactorScore.symbol == item.symbol))
            if row is None:
                row = FactorScore(symbol=item.symbol, as_of=now)
                self.session.add(row)
            row.technical = factors["technical"]
            row.tape = factors["tape"]
            row.regime_fit = factors["regime_fit"]
            row.news = factors["news"]
            row.quality = factors["quality"]
            row.composite = composite
            row.stance = stance
            row.detail_json = json.dumps({"weights": weights, "regime": regime})
            row.as_of = now
            if not item.stance:
                item.stance = stance
            written.append(row)
        self.session.flush()
        return written

    def latest(self) -> dict[str, FactorScore]:
        rows = list(self.session.scalars(select(FactorScore)))
        return {row.symbol: row for row in rows}
