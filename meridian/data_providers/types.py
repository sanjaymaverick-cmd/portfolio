from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class OhlcvBar:
    bar_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")


class MarketDataProvider(Protocol):
    def history(self, tickers: Sequence[str], period: str = "1y") -> dict[str, list[OhlcvBar]]:
        """Return daily bars keyed by the requested Yahoo ticker. Missing names are omitted."""
