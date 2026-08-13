from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.storage.schema import PriceBar, Quote, Setting


class SettingRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.session.get(Setting, key)
        return row.value if row else default

    def set(self, key: str, value: str) -> None:
        row = self.session.get(Setting, key)
        if row:
            row.value = value
        else:
            self.session.add(Setting(key=key, value=value))
        self.session.flush()


class QuoteRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, symbol: str, exchange: str) -> Quote | None:
        return self.session.scalar(
            select(Quote).where(Quote.symbol == symbol, Quote.exchange == exchange)
        )

    def get_yahoo(self, yahoo: str) -> Quote | None:
        return self.session.scalar(select(Quote).where(Quote.yahoo == yahoo))

    def upsert(
        self,
        *,
        symbol: str,
        exchange: str,
        yahoo: str,
        last_price,
        prev_close=None,
        as_of: datetime | None = None,
        source: str = "yfinance",
    ) -> Quote:
        row = self.get(symbol, exchange)
        now = datetime.now()
        if row:
            row.yahoo = yahoo
            row.last_price = last_price
            row.prev_close = prev_close
            row.as_of = as_of
            row.fetched_at = now
            row.source = source
            return row
        row = Quote(
            symbol=symbol,
            exchange=exchange,
            yahoo=yahoo,
            last_price=last_price,
            prev_close=prev_close,
            as_of=as_of,
            fetched_at=now,
            source=source,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def by_symbols(self, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        if not pairs:
            return {}
        rows = list(self.session.scalars(select(Quote)))
        wanted = set(pairs)
        return {(row.symbol, row.exchange): row for row in rows if (row.symbol, row.exchange) in wanted}


class BarRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, yahoo: str, limit: int = 260) -> list[PriceBar]:
        rows = list(
            self.session.scalars(
                select(PriceBar)
                .where(PriceBar.yahoo == yahoo)
                .order_by(PriceBar.bar_date.desc())
                .limit(limit)
            )
        )
        return list(reversed(rows))

    def last_date(self, yahoo: str) -> datetime | None:
        row = self.session.scalar(
            select(PriceBar).where(PriceBar.yahoo == yahoo).order_by(PriceBar.bar_date.desc())
        )
        return row.bar_date if row else None

    def count(self, yahoo: str) -> int:
        from sqlalchemy import func

        return int(
            self.session.scalar(select(func.count()).select_from(PriceBar).where(PriceBar.yahoo == yahoo))
            or 0
        )

    def replace_many(self, yahoo: str, bars: list[PriceBar]) -> None:
        if not bars:
            return
        existing = {
            row.bar_date.date() if hasattr(row.bar_date, "date") else row.bar_date: row
            for row in self.session.scalars(select(PriceBar).where(PriceBar.yahoo == yahoo))
        }
        for bar in bars:
            key = bar.bar_date.date() if hasattr(bar.bar_date, "date") else bar.bar_date
            current = existing.get(key)
            if current:
                current.open = bar.open
                current.high = bar.high
                current.low = bar.low
                current.close = bar.close
                current.volume = bar.volume
            else:
                self.session.add(bar)
        self.session.flush()
