"""Finished candles + markers for Lightweight Charts. No scoring math here."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence


def holding_chart_payload(symbol: str, yahoo: str, bars: Sequence[Any]) -> dict[str, Any]:
    candles = []
    closes: list[float] = []
    for bar in bars:
        day = bar.bar_date
        if isinstance(day, datetime):
            day = day.date()
        candles.append(
            {
                "time": day.isoformat(),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(getattr(bar, "volume", 0) or 0),
            }
        )
        closes.append(float(bar.close))
    signal = []
    window = 5
    run = 0.0
    for index, candle in enumerate(candles):
        run += closes[index]
        if index >= window:
            run -= closes[index - window]
        if index >= window - 1:
            signal.append({"time": candle["time"], "value": run / window})
    levels = []
    if len(closes) >= 20:
        levels.append({"price": sum(closes[-20:]) / 20, "title": "Slow average", "color": "#C4A35A"})
    return {
        "symbol": symbol,
        "label": yahoo,
        "quality": "ok" if candles else "missing",
        "candles": candles,
        "markers": [],
        "levels": levels,
        "zones": [],
        "windows": [],
        "signal": signal,
    }
