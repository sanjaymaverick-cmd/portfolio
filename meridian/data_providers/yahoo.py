from __future__ import annotations

import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from loguru import logger

from meridian.config import get_settings
from meridian.data_providers.types import OhlcvBar
from meridian.domain.money import to_decimal


class YahooProvider:
    """yfinance adapter. Batched, polite, never raises to the desk."""

    def __init__(self, sleep_ms: int | None = None, batch_size: int | None = None) -> None:
        settings = get_settings()
        self.sleep_ms = settings.providers.request_sleep_ms if sleep_ms is None else sleep_ms
        self.batch_size = settings.providers.batch_size if batch_size is None else batch_size

    def history(self, tickers: Sequence[str], period: str = "1y") -> dict[str, list[OhlcvBar]]:
        unique = [ticker for ticker in dict.fromkeys(tickers) if ticker]
        if not unique:
            return {}
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance is not installed")
            return {}

        out: dict[str, list[OhlcvBar]] = {}
        for start in range(0, len(unique), max(1, self.batch_size)):
            batch = unique[start : start + self.batch_size]
            try:
                frame = yf.download(
                    tickers=batch,
                    period=period,
                    interval="1d",
                    auto_adjust=False,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                    timeout=30,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("yfinance download failed for {}: {}", batch, exc)
                frame = None
            if frame is not None and not getattr(frame, "empty", True):
                out.update(_split_download(frame, batch))
            if start + self.batch_size < len(unique) and self.sleep_ms:
                time.sleep(self.sleep_ms / 1000)
        return out


def _split_download(frame: Any, tickers: Sequence[str]) -> dict[str, list[OhlcvBar]]:
    out: dict[str, list[OhlcvBar]] = {}
    if len(tickers) == 1 and not _is_multiindex(frame):
        bars = _rows_to_bars(frame)
        if bars:
            out[tickers[0]] = bars
        return out
    for ticker in tickers:
        slice_ = _ticker_frame(frame, ticker)
        if slice_ is None:
            continue
        bars = _rows_to_bars(slice_)
        if bars:
            out[ticker] = bars
    return out


def _is_multiindex(frame: Any) -> bool:
    columns = getattr(frame, "columns", None)
    return bool(columns is not None and getattr(columns, "nlevels", 1) > 1)


def _ticker_frame(frame: Any, ticker: str) -> Any | None:
    if ticker in frame.columns.get_level_values(0):
        return frame[ticker]
    # Some yfinance builds use (Field, Ticker)
    if _is_multiindex(frame) and ticker in frame.columns.get_level_values(-1):
        try:
            return frame.xs(ticker, axis=1, level=-1)
        except Exception:  # noqa: BLE001
            return None
    return None


def _rows_to_bars(frame: Any) -> list[OhlcvBar]:
    if frame is None or getattr(frame, "empty", True):
        return []
    renamed = {str(col).strip().lower(): col for col in frame.columns}
    close_key = _first(renamed, "close", "adj close")
    if close_key is None:
        return []
    bars: list[OhlcvBar] = []
    for index, row in frame.iterrows():
        close = to_decimal(row[renamed[close_key]])
        if close is None:
            continue
        open_ = to_decimal(row[renamed[_first(renamed, "open") or close_key]]) or close
        high = to_decimal(row[renamed[_first(renamed, "high") or close_key]]) or close
        low = to_decimal(row[renamed[_first(renamed, "low") or close_key]]) or close
        volume = to_decimal(row[renamed["volume"]]) if "volume" in renamed else Decimal("0")
        bar_date = _as_date(index)
        if bar_date is None:
            continue
        bars.append(
            OhlcvBar(
                bar_date=bar_date,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume or Decimal("0"),
            )
        )
    return bars


def _first(keys: dict[str, Any], *names: str) -> str | None:
    for name in names:
        if name in keys:
            return name
    return None


def _as_date(value: Any):
    try:
        ts = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
        if hasattr(ts, "date"):
            return ts.date()
    except Exception:  # noqa: BLE001
        return None
    return None
