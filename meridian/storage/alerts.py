from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.storage.schema import AlertEvent, WatchItem


class AlertRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, as_of: datetime, kind: str, symbol: str) -> AlertEvent | None:
        return self.session.scalar(
            select(AlertEvent).where(
                AlertEvent.as_of == _day(as_of),
                AlertEvent.kind == kind,
                AlertEvent.symbol == symbol.upper(),
            )
        )

    def upsert(self, row: AlertEvent) -> AlertEvent:
        row.as_of = _day(row.as_of)
        row.symbol = row.symbol.upper()
        existing = self.get(row.as_of, row.kind, row.symbol)
        if existing:
            existing.severity = row.severity
            existing.title = row.title
            existing.detail = row.detail
            existing.shap_note = row.shap_note
            existing.action = row.action
            existing.payload = row.payload
            if existing.status == "closed":
                existing.status = "open"
            self.session.flush()
            return existing
        self.session.add(row)
        self.session.flush()
        return row

    def close_missing(self, as_of: datetime, keep: set[tuple[str, str]]) -> int:
        day = _day(as_of)
        closed = 0
        for row in self.session.scalars(select(AlertEvent).where(AlertEvent.as_of == day)):
            if (row.kind, row.symbol) not in keep and row.status != "closed":
                row.status = "closed"
                closed += 1
        self.session.flush()
        return closed

    def open_alerts(self, as_of: datetime | None = None, *, limit: int | None = None) -> list[AlertEvent]:
        stmt = select(AlertEvent).where(AlertEvent.status == "open")
        if as_of is not None:
            stmt = stmt.where(AlertEvent.as_of == _day(as_of))
        stmt = stmt.order_by(AlertEvent.severity.asc(), AlertEvent.id.desc())
        rows = list(self.session.scalars(stmt))
        rank = {"high": 0, "watch": 1, "info": 2}
        rows.sort(key=lambda row: (rank.get(row.severity, 9), row.id))
        return rows[:limit] if limit else rows

    def recent(self, *, limit: int = 40) -> list[AlertEvent]:
        return list(self.session.scalars(select(AlertEvent).order_by(AlertEvent.id.desc()).limit(limit)))

    def ack(self, alert_id: int) -> AlertEvent | None:
        row = self.session.get(AlertEvent, alert_id)
        if row:
            row.status = "acked"
            self.session.flush()
        return row


class WatchRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[WatchItem]:
        return list(self.session.scalars(select(WatchItem).order_by(WatchItem.symbol)))

    def add(self, symbol: str, *, company_name: str | None = None, note: str | None = None) -> WatchItem:
        key = symbol.upper()
        row = self.session.get(WatchItem, key)
        if row:
            if company_name:
                row.company_name = company_name
            if note is not None:
                row.note = note
            self.session.flush()
            return row
        row = WatchItem(symbol=key, company_name=company_name, note=note)
        self.session.add(row)
        self.session.flush()
        return row

    def remove(self, symbol: str) -> None:
        row = self.session.get(WatchItem, symbol.upper())
        if row:
            self.session.delete(row)
            self.session.flush()


def _day(value: datetime) -> datetime:
    return datetime.combine(value.date(), datetime.min.time()) if hasattr(value, "date") else value
