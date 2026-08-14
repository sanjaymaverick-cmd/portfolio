"""Load candles for the chart layer. Models stay off this path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.config import get_settings
from meridian_v2.data_providers.service import YAHOO_COMMODITY_PROXY, YAHOO_FX
from meridian_v2.mcx.roll import ui_series_label
from meridian_v2.mcx.service import McxService
from meridian_v2.signals.chart_payload import (
    ChartLevel,
    ChartMarker,
    ChartWindow,
    ChartZone,
    build_chart_payload,
)
from meridian_v2.storage.schema import DeskEvent, PriceCache


@dataclass
class SimpleBar:
    bar_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def _ticker(symbol: str) -> str | None:
    if symbol in YAHOO_COMMODITY_PROXY:
        return YAHOO_COMMODITY_PROXY[symbol]
    if symbol in YAHOO_FX:
        return YAHOO_FX[symbol]
    if symbol.isalpha() and len(symbol) <= 12:
        return f"{symbol}.NS"
    return None


def fetch_history(symbol: str, *, period: str = "8mo") -> list[SimpleBar]:
    if get_settings().test_db:
        return []
    ticker = _ticker(symbol)
    if not ticker:
        return []
    try:
        import yfinance as yf
    except ImportError:
        return []
    try:
        hist = yf.Ticker(ticker).history(period=period)
    except Exception:
        return []
    if hist is None or hist.empty:
        return []
    bars: list[SimpleBar] = []
    for idx, row in hist.iterrows():
        day = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        bars.append(
            SimpleBar(
                bar_date=day,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]) if "Volume" in row else 0.0,
            )
        )
    return bars


def fallback_bars(row: PriceCache | None) -> list[SimpleBar]:
    if row is None or row.last is None:
        return []
    last = float(row.last)
    prev = float(row.prev_close or last)
    day = (row.as_of.date() if row.as_of else date.today())
    earlier = day - timedelta(days=1)
    return [
        SimpleBar(earlier, prev, max(prev, last), min(prev, last), prev),
        SimpleBar(day, prev, max(prev, last), min(prev, last), last, float(row.volume or 0)),
    ]


def chart_for_symbol(session: Session, symbol: str) -> dict[str, Any]:
    cache = session.scalar(
        select(PriceCache).where(
            PriceCache.symbol == symbol, PriceCache.contract_label == "CONTINUOUS"
        )
    )
    specs = {spec.symbol_key: spec for spec in McxService(session).specs()}
    label = ui_series_label(specs[symbol]) if symbol in specs else symbol
    quality = cache.quality if cache else "missing"
    bars = fetch_history(symbol) or fallback_bars(cache)
    markers: list[ChartMarker] = []
    for event in session.scalars(
        select(DeskEvent).where(DeskEvent.symbol == symbol).order_by(DeskEvent.created_at.desc()).limit(12)
    ):
        blob = f"{event.reason or ''} {event.copy_review or ''} {event.rule_name or ''}".lower()
        side = "short" if any(word in blob for word in ("sell", "short", "cut", "trim")) else "long"
        score = int(round(abs(event.strength or 0) * 100)) or None
        label = "Look at a short / exit" if side == "short" else "Look at a long / entry"
        markers.append(
            ChartMarker(
                time=event.created_at.date().isoformat(),
                side=side,
                text=label,
                confidence=score,
            )
        )
    levels: list[ChartLevel] = []
    zones: list[ChartZone] = []
    if cache and cache.high20 and cache.low20:
        levels.append(ChartLevel(float(cache.sma20 or cache.last or 0), "Slow average"))
        zones.append(ChartZone(float(cache.low20), float(cache.high20), "Recent range"))
    windows: list[ChartWindow] = []
    if markers:
        latest = max(markers, key=lambda item: item.time)
        start = (date.fromisoformat(latest.time) - timedelta(days=5)).isoformat()
        windows.append(
            ChartWindow(
                start,
                latest.time,
                "Higher-attention window",
                "rgba(74,155,127,0.10)" if latest.side == "long" else "rgba(196,107,107,0.10)",
            )
        )
    elif bars:
        last = bars[-1].bar_date
        windows.append(
            ChartWindow(
                (last - timedelta(days=10)).isoformat(),
                last.isoformat(),
                "Recent window",
            )
        )
    return build_chart_payload(
        symbol=symbol,
        label=label,
        quality=quality,
        bars=bars,
        markers=markers,
        levels=levels,
        zones=zones,
        windows=windows,
    ).as_dict()
