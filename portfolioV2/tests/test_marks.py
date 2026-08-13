from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select

from meridian_v2.data_providers.service import apply_cached_marks
from meridian_v2.storage.schema import BookLegRow, PriceCache


def test_apply_cached_marks_updates_inventory_not_equity_label(session):
    now = datetime.now(UTC).replace(tzinfo=None)
    session.add(
        PriceCache(
            symbol="GOLD",
            contract_label="CONTINUOUS",
            series_kind="CONTINUOUS",
            last=73000.0,
            prev_close=72000.0,
            as_of=now,
            quality="proxy",
            source="yahoo_international_proxy",
        )
    )
    session.add(
        BookLegRow(
            leg_id="g1",
            symbol="GOLD",
            asset_class="commodity",
            lots=2,
            multiplier=100,
            mark_inr=72000,
            contract_label="CONTINUOUS",
            as_of=date.today(),
        )
    )
    session.flush()
    assert apply_cached_marks(session) == 1
    session.flush()
    row = session.scalar(select(BookLegRow).where(BookLegRow.leg_id == "g1"))
    assert row is not None
    assert row.mark_inr == 73000.0
    assert row.contract_label == "CONTINUOUS"
