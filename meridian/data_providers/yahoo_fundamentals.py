from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from loguru import logger

from meridian.data_providers.screener import FundamentalSnap
from meridian.domain.money import safe_div


class YahooFundamentals:
    """Degraded path when Screener.in is unreachable."""

    def fetch(self, symbol: str, yahoo: str) -> FundamentalSnap | None:
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            info = yf.Ticker(yahoo).info or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("yahoo fundamentals failed for {}: {}", yahoo, exc)
            return None
        if not info:
            return None
        roe = _pct(info.get("returnOnEquity"))
        roce = _pct(info.get("returnOnAssets"))  # weaker proxy
        opm = _pct(info.get("operatingMargins") or info.get("profitMargins"))
        pe = _dec(info.get("trailingPE") or info.get("forwardPE"))
        pb = _dec(info.get("priceToBook"))
        ev = _dec(info.get("enterpriseToEbitda"))
        price = _dec(info.get("currentPrice") or info.get("regularMarketPrice"))
        book = safe_div(price, pb)
        de = _dec(info.get("debtToEquity"))
        if de is not None and de > 5:
            de = de / Decimal("100")
        return FundamentalSnap(
            symbol=symbol.upper(),
            source="yfinance",
            company_name=info.get("shortName") or info.get("longName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            current_price=price,
            pe=pe,
            book_value=book,
            pb=pb,
            dividend_yield=_pct(info.get("dividendYield")),
            roce=roce,
            roe=roe,
            opm=opm,
            debt_to_equity=de,
            ev_ebitda=ev,
            as_of=datetime.now(),
            notes="Screener unavailable; yfinance snapshot.",
        )


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _pct(value: object) -> Decimal | None:
    number = _dec(value)
    if number is None:
        return None
    if abs(number) <= 2:
        return number * Decimal("100")
    return number
