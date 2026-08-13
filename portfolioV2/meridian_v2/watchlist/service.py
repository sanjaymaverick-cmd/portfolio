from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meridian_v2.config import get_settings
from meridian_v2.domain.models import AssetClass, WatchStatus
from meridian_v2.storage.schema import WatchCatalyst, WatchItem


class WatchlistError(ValueError):
    pass


class WatchlistService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.cap = get_settings().watchlist.active_cap

    def active_count(self) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(WatchItem).where(
                    WatchItem.status == WatchStatus.ACTIVE.value
                )
            )
            or 0
        )

    def list_items(self, *, status: str | None = None) -> list[WatchItem]:
        stmt = select(WatchItem).order_by(WatchItem.symbol)
        if status:
            stmt = stmt.where(WatchItem.status == status)
        return list(self.session.scalars(stmt))

    def active(self) -> list[WatchItem]:
        return self.list_items(status=WatchStatus.ACTIVE.value)

    def cap_state(self) -> dict:
        active = self.active_count()
        remaining = max(0, self.cap - active)
        return {
            "active": active,
            "cap": self.cap,
            "remaining": remaining,
            "at_cap": active >= self.cap,
            "warn": active >= self.cap or remaining <= max(5, self.cap // 10),
        }

    def add(
        self,
        symbol: str,
        asset_class: str,
        notes: str = "",
        *,
        stance: str = "",
        sector: str = "",
    ) -> WatchItem:
        symbol = symbol.strip().upper()
        if not symbol:
            raise WatchlistError("symbol is required")
        try:
            AssetClass(asset_class)
        except ValueError as exc:
            raise WatchlistError(f"unknown asset_class: {asset_class}") from exc
        existing = self.session.scalar(select(WatchItem).where(WatchItem.symbol == symbol))
        if existing:
            if existing.status == WatchStatus.ARCHIVED.value:
                return self.restore(existing.id)
            raise WatchlistError(f"{symbol} is already on the active watchlist")
        if self.active_count() >= self.cap:
            raise WatchlistError(
                f"active watchlist is at the soft cap of {self.cap}; archive a name before adding"
            )
        now = datetime.now(UTC).replace(tzinfo=None)
        item = WatchItem(
            symbol=symbol,
            asset_class=asset_class,
            status=WatchStatus.ACTIVE.value,
            notes=notes.strip(),
            stance=stance if stance in {"consider", "avoid", "wait"} else "",
            sector=sector.strip(),
            created_at=now,
            updated_at=now,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def archive(self, item_id: int) -> WatchItem:
        item = self.session.get(WatchItem, item_id)
        if item is None:
            raise WatchlistError("watch item not found")
        item.status = WatchStatus.ARCHIVED.value
        item.updated_at = datetime.now(UTC).replace(tzinfo=None)
        return item

    def restore(self, item_id: int) -> WatchItem:
        item = self.session.get(WatchItem, item_id)
        if item is None:
            raise WatchlistError("watch item not found")
        if item.status == WatchStatus.ACTIVE.value:
            return item
        if self.active_count() >= self.cap:
            raise WatchlistError(
                f"active watchlist is at the soft cap of {self.cap}; archive a name before restore"
            )
        item.status = WatchStatus.ACTIVE.value
        item.updated_at = datetime.now(UTC).replace(tzinfo=None)
        return item

    def remove(self, item_id: int) -> None:
        item = self.session.get(WatchItem, item_id)
        if item is None:
            raise WatchlistError("watch item not found")
        for cat in list(self.session.scalars(select(WatchCatalyst).where(WatchCatalyst.watch_id == item_id))):
            self.session.delete(cat)
        self.session.delete(item)

    def set_stance(self, item_id: int, stance: str) -> WatchItem:
        item = self.session.get(WatchItem, item_id)
        if item is None:
            raise WatchlistError("watch item not found")
        if stance not in {"", "consider", "avoid", "wait"}:
            raise WatchlistError("stance must be consider, avoid, or wait")
        item.stance = stance
        item.updated_at = datetime.now(UTC).replace(tzinfo=None)
        return item

    def add_catalyst(
        self,
        item_id: int,
        kind: str,
        *,
        event_date: date | None = None,
        level: float | None = None,
        notes: str = "",
    ) -> WatchCatalyst:
        item = self.session.get(WatchItem, item_id)
        if item is None:
            raise WatchlistError("watch item not found")
        row = WatchCatalyst(
            watch_id=item_id,
            kind=kind.strip() or "event",
            event_date=event_date,
            level=level,
            notes=notes.strip(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def catalysts(self, item_id: int) -> list[WatchCatalyst]:
        return list(
            self.session.scalars(select(WatchCatalyst).where(WatchCatalyst.watch_id == item_id))
        )
