from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.config import get_settings
from meridian_v2.storage.schema import BookLegRow, FxMark, HedgeLegRow, PriceCache

YAHOO_FX = {
    "USDINR": "USDINR=X",
    "EURUSD": "EURUSD=X",
    "USDJPY": "USDJPY=X",
}

# International proxies — never labelled as MCX contracts.
YAHOO_COMMODITY_PROXY = {
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "CRUDEOIL": "CL=F",
    "COPPER": "HG=F",
    "NATURALGAS": "NG=F",
}


class PriceProvider:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()

    def refresh(self, *, force: bool = False) -> dict[str, int]:
        marked = 0
        failed = 0
        if not self.settings.providers.yfinance_enabled:
            applied = apply_cached_marks(self.session)
            return {"marked": 0, "failed": 0, "skipped": 1, "applied": applied}
        try:
            import yfinance as yf
        except ImportError:
            return {"marked": 0, "failed": 1, "skipped": 0}

        now = datetime.now(UTC).replace(tzinfo=None)
        for pair, ticker in YAHOO_FX.items():
            last, prev = _last_prev(yf, ticker)
            if last is None:
                failed += 1
                continue
            row = self.session.scalar(select(FxMark).where(FxMark.pair == pair))
            if row is None:
                row = FxMark(pair=pair, last=last, prev_close=prev, as_of=now, quality="ok", source="yahoo")
                self.session.add(row)
            else:
                row.last, row.prev_close, row.as_of = last, prev, now
                row.quality, row.source = "ok", "yahoo"
            marked += 1

        for symbol, ticker in YAHOO_COMMODITY_PROXY.items():
            stats = _tape_stats(yf, ticker)
            last, prev = stats["last"], stats["prev"]
            quality = "proxy" if last is not None else "missing"
            source = "yahoo_international_proxy"
            row = self.session.scalar(
                select(PriceCache).where(
                    PriceCache.symbol == symbol,
                    PriceCache.contract_label == "CONTINUOUS",
                )
            )
            if row is None:
                row = PriceCache(
                    symbol=symbol,
                    contract_label="CONTINUOUS",
                    series_kind="CONTINUOUS",
                    last=last,
                    prev_close=prev,
                    as_of=now,
                    quality=quality,
                    source=source,
                )
                self.session.add(row)
            else:
                row.last, row.prev_close, row.as_of = last, prev, now
                row.quality, row.source = quality, source
            row.sma20 = stats["sma20"]
            row.sma50 = stats["sma50"]
            row.weekly_last = stats["weekly_last"]
            row.weekly_sma = stats["weekly_sma"]
            row.high20 = stats["high20"]
            row.low20 = stats["low20"]
            row.volume = stats["volume"]
            row.prev_volume = stats["prev_volume"]
            if last is None:
                failed += 1
            else:
                marked += 1
        applied = apply_cached_marks(self.session)
        return {"marked": marked, "failed": failed, "skipped": 0, "applied": applied}


def apply_cached_marks(session: Session) -> int:
    """Push CONTINUOUS cache onto futures/inventory legs. Never relabel as equity tickers."""
    prices = {
        row.symbol: row.last
        for row in session.scalars(select(PriceCache).where(PriceCache.contract_label == "CONTINUOUS"))
        if row.last is not None
    }
    applied = 0
    for model in (BookLegRow, HedgeLegRow):
        for row in session.scalars(select(model)):
            mark = prices.get(row.symbol)
            if mark is None:
                continue
            row.mark_inr = mark
            applied += 1
    return applied


def _last_prev(yf, ticker: str) -> tuple[float | None, float | None]:
    stats = _tape_stats(yf, ticker, period="5d")
    return stats["last"], stats["prev"]


def _tape_stats(yf, ticker: str, period: str = "8mo") -> dict:
    empty = {
        "last": None,
        "prev": None,
        "sma20": None,
        "sma50": None,
        "weekly_last": None,
        "weekly_sma": None,
        "high20": None,
        "low20": None,
        "volume": None,
        "prev_volume": None,
    }
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist is None or hist.empty:
            return empty
        close = hist["Close"].dropna()
        if close.empty:
            return empty
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else last
        vol = hist["Volume"].dropna() if "Volume" in hist.columns else None
        weekly = close.resample("W").last().dropna()
        empty.update(
            {
                "last": last,
                "prev": prev,
                "sma20": float(close.tail(20).mean()) if len(close) >= 5 else last,
                "sma50": float(close.tail(50).mean()) if len(close) >= 10 else last,
                "weekly_last": float(weekly.iloc[-1]) if len(weekly) else last,
                "weekly_sma": float(weekly.tail(10).mean()) if len(weekly) >= 4 else last,
                "high20": float(close.tail(20).max()),
                "low20": float(close.tail(20).min()),
                "volume": float(vol.iloc[-1]) if vol is not None and len(vol) else None,
                "prev_volume": float(vol.iloc[-2]) if vol is not None and len(vol) > 1 else None,
            }
        )
        return empty
    except Exception:
        return empty
