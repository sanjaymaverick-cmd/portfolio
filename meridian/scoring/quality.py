from __future__ import annotations

from decimal import Decimal

from meridian.data_providers.screener import FundamentalSnap
from meridian.scoring.bands import CFO, DE, GROWTH, OPM, ROCE, ROE, interpolate

WEIGHTS = {
    "roe": Decimal("0.22"),
    "roce": Decimal("0.22"),
    "margins": Decimal("0.18"),
    "leverage": Decimal("0.16"),
    "cashflow": Decimal("0.12"),
    "growth": Decimal("0.10"),
}


def score_quality(snap: FundamentalSnap) -> tuple[Decimal | None, dict[str, Decimal | None]]:
    parts: dict[str, Decimal | None] = {
        "roe": interpolate(snap.roe, ROE),
        "roce": interpolate(snap.roce, ROCE),
        "margins": _margin_score(snap),
        "leverage": _leverage_score(snap),
        "cashflow": interpolate(snap.cfo_to_op, CFO),
        "growth": _growth_score(snap),
    }
    return _weighted(parts, WEIGHTS), parts


def _margin_score(snap: FundamentalSnap) -> Decimal | None:
    level = interpolate(snap.opm, OPM)
    if level is None:
        return None
    if snap.opm_5y_std is None:
        return level
    # Unstable margins lose up to 1.5 points.
    penalty = min(Decimal("1.5"), (snap.opm_5y_std / Decimal("4")) * Decimal("1.5"))
    return max(Decimal("0"), level - penalty)


def _leverage_score(snap: FundamentalSnap) -> Decimal | None:
    sector = (snap.sector or "").lower()
    if "financial" in sector or "bank" in sector:
        return None
    return interpolate(snap.debt_to_equity, DE)


def _growth_score(snap: FundamentalSnap) -> Decimal | None:
    samples = [
        interpolate(snap.sales_cagr_5y, GROWTH),
        interpolate(snap.sales_cagr_3y, GROWTH),
        interpolate(snap.profit_cagr_5y, GROWTH),
        interpolate(snap.profit_cagr_3y, GROWTH),
    ]
    present = [item for item in samples if item is not None]
    if not present:
        return None
    return sum(present, Decimal("0")) / Decimal(len(present))


def _weighted(
    parts: dict[str, Decimal | None], weights: dict[str, Decimal]
) -> Decimal | None:
    total = Decimal("0")
    mass = Decimal("0")
    for key, score in parts.items():
        if score is None:
            continue
        weight = weights[key]
        total += score * weight
        mass += weight
    if mass == 0:
        return None
    return (total / mass).quantize(Decimal("0.01"))
