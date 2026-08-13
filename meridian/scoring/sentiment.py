from __future__ import annotations

from decimal import Decimal

from meridian.data_providers.screener import FundamentalSnap
from meridian.scoring.bands import interpolate
from meridian.scoring.quality import _weighted

_NEG = (
    "low",
    "declin",
    "debt",
    "pledged",
    "weak",
    "fall",
    "loss",
    "dilut",
    "impair",
    "concern",
    "high interest",
)
_POS = (
    "growth",
    "debt-free",
    "strong",
    "increase",
    "healthy",
    "surplus",
    "consistent",
    "high return",
    "dividend",
)

WEIGHTS = {
    "balance": Decimal("0.70"),
    "tone": Decimal("0.30"),
}


def score_sentiment(snap: FundamentalSnap) -> tuple[Decimal | None, dict[str, Decimal | None]]:
    if not snap.pros and not snap.cons:
        return None, {"balance": None, "tone": None}
    balance = interpolate(
        Decimal(len(snap.pros) - len(snap.cons)),
        [(-4, 2.2), (-2, 3.6), (0, 5.4), (2, 7.2), (4, 8.8)],
    )
    tone = _tone(snap.pros, snap.cons)
    parts = {"balance": balance, "tone": tone}
    return _weighted(parts, WEIGHTS), parts


def _tone(pros: list[str], cons: list[str]) -> Decimal:
    score = 0
    for line in pros:
        low = line.lower()
        score += 1 + sum(1 for token in _POS if token in low)
        score -= sum(1 for token in _NEG if token in low)
    for line in cons:
        low = line.lower()
        score -= 1 + sum(1 for token in _NEG if token in low)
        score += sum(1 for token in _POS if token in low)
    return interpolate(Decimal(score), [(-8, 2.0), (-3, 3.8), (0, 5.4), (3, 7.2), (8, 9.0)]) or Decimal("5.0")
