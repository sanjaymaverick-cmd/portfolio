from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meridian.storage.schema import DailyImpact, DailyNews, DailyPerformance


class EodRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def clear_day(self, as_of: datetime) -> None:
        day = _day(as_of)
        self.session.execute(delete(DailyNews).where(DailyNews.as_of == day))
        self.session.execute(delete(DailyImpact).where(DailyImpact.as_of == day))
        self.session.execute(delete(DailyPerformance).where(DailyPerformance.as_of == day))
        self.session.flush()

    def add_perf(self, row: DailyPerformance) -> DailyPerformance:
        row.as_of = _day(row.as_of)
        self.session.add(row)
        self.session.flush()
        return row

    def add_news(self, row: DailyNews) -> DailyNews:
        row.as_of = _day(row.as_of)
        self.session.add(row)
        self.session.flush()
        return row

    def upsert_impact(self, row: DailyImpact) -> DailyImpact:
        row.as_of = _day(row.as_of)
        existing = self.session.scalar(
            select(DailyImpact).where(DailyImpact.as_of == row.as_of, DailyImpact.symbol == row.symbol)
        )
        if existing:
            existing.engine = row.engine
            existing.takeaway = row.takeaway
            existing.market_context = row.market_context
            existing.confidence = row.confidence
            existing.positives = row.positives
            existing.negatives = row.negatives
            existing.payload = row.payload
            self.session.flush()
            return existing
        self.session.add(row)
        self.session.flush()
        return row

    def latest_day(self) -> datetime | None:
        row = self.session.scalar(select(DailyPerformance).order_by(DailyPerformance.as_of.desc()))
        return row.as_of if row else None

    def movers(self, as_of: datetime | None = None) -> list[tuple[DailyPerformance, DailyImpact | None]]:
        day = as_of or self.latest_day()
        if day is None:
            return []
        day = _day(day)
        perfs = list(
            self.session.scalars(
                select(DailyPerformance)
                .where(DailyPerformance.as_of == day, DailyPerformance.selected.is_(True))
                .order_by(DailyPerformance.day_pnl_pct.desc())
            )
        )
        out: list[tuple[DailyPerformance, DailyImpact | None]] = []
        for perf in perfs:
            impact = self.session.scalar(
                select(DailyImpact).where(DailyImpact.as_of == day, DailyImpact.symbol == perf.symbol)
            )
            out.append((perf, impact))
        return out

    def timeline(self, symbol: str, limit: int = 8) -> list[DailyImpact]:
        return list(
            self.session.scalars(
                select(DailyImpact)
                .where(DailyImpact.symbol == symbol.upper())
                .order_by(DailyImpact.as_of.desc())
                .limit(limit)
            )
        )

    def news_for(self, as_of: datetime, symbol: str) -> list[DailyNews]:
        return list(
            self.session.scalars(
                select(DailyNews)
                .where(DailyNews.as_of == _day(as_of), DailyNews.symbol == symbol.upper(), DailyNews.kept.is_(True))
                .order_by(DailyNews.rank.desc())
            )
        )


def decode_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _day(value: datetime) -> datetime:
    return datetime.combine(value.date(), datetime.min.time()) if hasattr(value, "date") else value
