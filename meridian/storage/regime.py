from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.storage.schema import FilterState, RegimeSnapshot


class FilterStateRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, key: str) -> dict | None:
        row = self.session.get(FilterState, key)
        if not row:
            return None
        try:
            return json.loads(row.payload)
        except json.JSONDecodeError:
            return None

    def set(self, key: str, payload: dict) -> None:
        text = json.dumps(payload)
        row = self.session.get(FilterState, key)
        now = datetime.now()
        if row:
            row.payload = text
            row.updated_at = now
        else:
            self.session.add(FilterState(key=key, payload=text, updated_at=now))
        self.session.flush()


class RegimeRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self) -> RegimeSnapshot | None:
        return self.session.scalar(select(RegimeSnapshot).order_by(RegimeSnapshot.as_of.desc()))

    def get(self, as_of: datetime) -> RegimeSnapshot | None:
        day = datetime.combine(as_of.date(), datetime.min.time()) if hasattr(as_of, "date") else as_of
        return self.session.get(RegimeSnapshot, day)

    def previous(self, as_of: datetime) -> RegimeSnapshot | None:
        day = datetime.combine(as_of.date(), datetime.min.time()) if hasattr(as_of, "date") else as_of
        return self.session.scalar(
            select(RegimeSnapshot)
            .where(RegimeSnapshot.as_of < day)
            .order_by(RegimeSnapshot.as_of.desc())
        )

    def upsert(self, snap: RegimeSnapshot) -> RegimeSnapshot:
        day = datetime.combine(snap.as_of.date(), datetime.min.time())
        existing = self.session.get(RegimeSnapshot, day)
        snap.as_of = day
        if existing:
            existing.label = snap.label
            existing.soft_calm = snap.soft_calm
            existing.soft_elevated = snap.soft_elevated
            existing.soft_stress = snap.soft_stress
            existing.vix = snap.vix
            existing.ewma_vol_ann = snap.ewma_vol_ann
            existing.kalman_trend_z = snap.kalman_trend_z
            existing.nifty_vs_sma50 = snap.nifty_vs_sma50
            existing.reason = snap.reason
            existing.vix_source = snap.vix_source
            existing.computed_at = datetime.now()
            self.session.flush()
            return existing
        self.session.add(snap)
        self.session.flush()
        return snap


def dec(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(value, 6)))
