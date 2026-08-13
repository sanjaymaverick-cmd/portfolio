"""Read-only import of a v1 holdings *snapshot*. Never opens v1 for writes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from meridian_v2.watchlist.service import WatchlistError, WatchlistService

DEFAULT_V1_DB = Path(__file__).resolve().parents[3] / "data" / "meridian.db"


def import_v1_holdings_snapshot(session: Session, db_path: Path | None = None) -> tuple[int, int]:
    path = db_path or DEFAULT_V1_DB
    if not path.exists():
        raise FileNotFoundError(f"v1 db not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(holdings)")}
        symbol_col = "symbol" if "symbol" in cols else None
        if symbol_col is None:
            raise ValueError("v1 holdings table has no symbol column")
        extra = ", company_name" if "company_name" in cols else ""
        rows = list(conn.execute(f"SELECT DISTINCT symbol{extra} FROM holdings"))
    finally:
        conn.close()
    svc = WatchlistService(session)
    accepted = 0
    rejected = 0
    now = datetime.now(UTC).replace(tzinfo=None)
    for row in rows:
        symbol = str(row[0] or "").upper()
        note = f"Imported read-only from v1 snapshot {now.date()}"
        if len(row) > 1 and row[1]:
            note = f"{row[1]} · {note}"
        if not symbol:
            rejected += 1
            continue
        try:
            item = svc.add(symbol, "equity", note)
            item.notes = note
            accepted += 1
        except WatchlistError:
            rejected += 1
    return accepted, rejected
