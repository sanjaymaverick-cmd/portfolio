from __future__ import annotations

from decimal import Decimal

from meridian.data_providers.screener import FundamentalSnap
from meridian.scoring.bands import interpolate
from meridian.scoring.quality import _weighted

WEIGHTS = {
    "promoter": Decimal("0.35"),
    "pledge": Decimal("0.30"),
    "fii_trend": Decimal("0.20"),
    "dii_trend": Decimal("0.15"),
}


def score_ownership(snap: FundamentalSnap) -> tuple[Decimal | None, dict[str, Decimal | None]]:
    parts: dict[str, Decimal | None] = {
        "promoter": interpolate(snap.promoter_pct, [(20, 2.4), (35, 5.2), (50, 8.0), (65, 8.6), (80, 6.4), (90, 4.2)]),
        "pledge": _pledge(snap.promoter_pledge),
        "fii_trend": _flow(snap.fii_delta, snap.fii_pct),
        "dii_trend": _flow(snap.dii_delta, snap.dii_pct),
    }
    return _weighted(parts, WEIGHTS), parts


def _pledge(value: Decimal | None) -> Decimal | None:
    if value is None:
        return Decimal("8.0")  # not disclosed — treat as clean, slightly discounted
    return interpolate(value, [(0, 9.8), (2, 8.2), (8, 5.4), (15, 3.0), (30, 1.2)])


def _flow(delta: Decimal | None, level: Decimal | None) -> Decimal | None:
    if delta is None and level is None:
        return None
    trend = interpolate(delta, [(-3.0, 2.4), (-1.0, 4.2), (0.0, 5.6), (0.8, 7.6), (2.5, 9.0)])
    size = interpolate(level, [(2, 3.4), (8, 5.5), (18, 7.4), (30, 8.0), (45, 6.5)])
    present = [item for item in (trend, size) if item is not None]
    if not present:
        return None
    return sum(present, Decimal("0")) / Decimal(len(present))
