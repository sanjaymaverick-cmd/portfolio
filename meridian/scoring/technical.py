from __future__ import annotations

from decimal import Decimal

from meridian.scoring.bands import interpolate
from meridian.scoring.quality import _weighted

WEIGHTS = {
    "trend": Decimal("0.40"),
    "rsi": Decimal("0.20"),
    "rs": Decimal("0.25"),
    "volume": Decimal("0.15"),
}


def score_technical(
    *,
    last: float | None,
    sma20: float | None,
    sma50: float | None,
    sma200: float | None,
    rsi: float | None,
    rs_nifty: float | None,
    volume_ratio: float | None,
) -> tuple[Decimal | None, dict[str, Decimal | None]]:
    parts: dict[str, Decimal | None] = {
        "trend": _trend(last, sma20, sma50, sma200),
        "rsi": interpolate(rsi, [(20, 3.2), (30, 5.4), (45, 7.2), (58, 7.6), (70, 5.0), (82, 2.8)]),
        "rs": interpolate(
            None if rs_nifty is None else rs_nifty * 100,
            [(-20, 2.2), (-8, 4.0), (0, 5.6), (8, 7.4), (18, 8.8)],
        ),
        "volume": interpolate(volume_ratio, [(0.4, 3.2), (0.8, 5.2), (1.1, 6.8), (1.6, 8.0), (2.4, 7.2)]),
    }
    return _weighted(parts, WEIGHTS), parts


def _trend(
    last: float | None,
    sma20: float | None,
    sma50: float | None,
    sma200: float | None,
) -> Decimal | None:
    if last is None:
        return None
    flags: list[bool] = []
    for level in (sma20, sma50, sma200):
        if level is not None:
            flags.append(last >= level)
    if not flags:
        return None
    above = sum(1 for item in flags if item)
    stacked = 10.0 * above / len(flags)
    if sma20 is not None and sma50 is not None and sma20 >= sma50:
        stacked += 0.4
    if sma50 is not None and sma200 is not None and sma50 >= sma200:
        stacked += 0.4
    return Decimal(str(round(min(10.0, stacked), 2)))
