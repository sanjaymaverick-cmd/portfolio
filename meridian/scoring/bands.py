from __future__ import annotations

from decimal import Decimal

# (x, score) knots. Interpolated. High-better unless noted.


def interpolate(value: Decimal | float | None, knots: list[tuple[float, float]]) -> Decimal | None:
    if value is None:
        return None
    x = float(value)
    ordered = sorted(knots, key=lambda item: item[0])
    if x <= ordered[0][0]:
        return _clamp(ordered[0][1])
    if x >= ordered[-1][0]:
        return _clamp(ordered[-1][1])
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:], strict=False):
        if x0 <= x <= x1:
            if x1 == x0:
                return _clamp(y1)
            t = (x - x0) / (x1 - x0)
            return _clamp(y0 + t * (y1 - y0))
    return _clamp(ordered[-1][1])


def _clamp(score: float) -> Decimal:
    return Decimal(str(round(max(0.0, min(10.0, score)), 2)))


ROE = [(-8.0, 0.8), (0.0, 2.0), (8.0, 4.4), (12.0, 6.0), (15.0, 7.2), (20.0, 8.6), (25.0, 9.4), (35.0, 10.0)]
ROCE = [(-5.0, 1.0), (0.0, 2.2), (8.0, 4.6), (12.0, 6.2), (16.0, 7.5), (22.0, 8.8), (30.0, 10.0)]
OPM = [(0.0, 2.0), (6.0, 4.2), (12.0, 6.0), (18.0, 7.4), (25.0, 8.6), (35.0, 9.6)]
DE = [(0.0, 9.6), (0.3, 8.4), (0.6, 7.0), (1.0, 5.2), (1.6, 3.4), (2.5, 2.0), (4.0, 1.0)]  # low better
CFO = [(0.0, 1.6), (0.4, 3.4), (0.7, 5.4), (1.0, 7.6), (1.2, 8.8), (1.6, 9.6)]
GROWTH = [(-8.0, 1.4), (0.0, 3.2), (6.0, 5.4), (12.0, 7.2), (18.0, 8.6), (28.0, 9.6)]
PE = [(8.0, 9.4), (12.0, 8.2), (16.0, 7.0), (22.0, 5.6), (30.0, 4.0), (42.0, 2.6), (65.0, 1.4)]  # low better
PB = [(0.8, 9.2), (1.5, 7.8), (2.5, 6.2), (4.0, 4.6), (7.0, 3.0), (12.0, 1.8)]
EV = [(6.0, 9.2), (9.0, 7.8), (12.0, 6.4), (16.0, 4.8), (22.0, 3.2), (32.0, 1.8)]

SECTOR_TYPICAL: dict[str, dict[str, float]] = {
    "information technology": {"pe": 26, "pb": 7.0, "ev": 18},
    "financials": {"pe": 16, "pb": 2.4, "ev": 11},
    "energy": {"pe": 14, "pb": 2.0, "ev": 9},
    "fmcg": {"pe": 42, "pb": 10.0, "ev": 24},
    "consumer discretionary": {"pe": 48, "pb": 12.0, "ev": 28},
    "automobile": {"pe": 24, "pb": 4.5, "ev": 14},
    "healthcare": {"pe": 32, "pb": 5.5, "ev": 18},
    "industrials": {"pe": 28, "pb": 5.0, "ev": 16},
    "materials": {"pe": 20, "pb": 3.2, "ev": 11},
    "telecom": {"pe": 22, "pb": 3.8, "ev": 10},
    "utilities": {"pe": 18, "pb": 2.2, "ev": 10},
    "oil, gas & consumable fuels": {"pe": 13, "pb": 1.8, "ev": 8},
}


def typical_for(sector: str | None, industry: str | None = None) -> dict[str, float]:
    for key in (industry or "", sector or ""):
        hit = SECTOR_TYPICAL.get(key.lower())
        if hit:
            return hit
    return {"pe": 22, "pb": 3.5, "ev": 14}
