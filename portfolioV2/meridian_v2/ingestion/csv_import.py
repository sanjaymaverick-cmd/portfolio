"""Manual equity/commodity CSV import — watch or book legs. No broker."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from meridian_v2.storage.schema import BookLegRow
from meridian_v2.watchlist.service import WatchlistError, WatchlistService


def import_watch_csv(session: Session, path: Path) -> tuple[int, int]:
    accepted = 0
    rejected = 0
    svc = WatchlistService(session)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = { (k or "").strip().lower(): (v or "").strip() for k, v in raw.items() }
            symbol = (row.get("symbol") or row.get("ticker") or "").upper()
            asset = (row.get("asset_class") or row.get("class") or "equity").lower()
            notes = row.get("notes") or row.get("note") or ""
            if not symbol:
                rejected += 1
                continue
            try:
                item = svc.add(symbol, asset if asset in {"equity", "commodity", "fx"} else "equity", notes)
                if row.get("stance") in {"consider", "avoid", "wait"}:
                    item.stance = row["stance"]
                if row.get("sector"):
                    item.sector = row["sector"]
                accepted += 1
            except WatchlistError:
                rejected += 1
    return accepted, rejected


def import_book_csv(session: Session, path: Path) -> tuple[int, int]:
    accepted = 0
    rejected = 0
    now = date.today()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for i, raw in enumerate(reader, start=1):
            row = { (k or "").strip().lower(): (v or "").strip() for k, v in raw.items() }
            symbol = (row.get("symbol") or "").upper()
            try:
                lots = float(row.get("lots") or row.get("qty") or row.get("quantity") or 0)
                mark = float(row.get("mark") or row.get("price") or row.get("last") or 0)
                mult = float(row.get("multiplier") or 1)
            except ValueError:
                rejected += 1
                continue
            if not symbol or lots == 0:
                rejected += 1
                continue
            session.add(
                BookLegRow(
                    leg_id=f"csv-{symbol}-{i}-{datetime.now(UTC).timestamp():.0f}",
                    symbol=symbol,
                    asset_class=row.get("asset_class") or "equity",
                    lots=lots,
                    multiplier=mult,
                    mark_inr=mark,
                    contract_label=row.get("contract") or "CONTINUOUS",
                    as_of=now,
                )
            )
            accepted += 1
    session.flush()
    return accepted, rejected
