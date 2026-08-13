from __future__ import annotations

from datetime import UTC, datetime

from meridian_v2.scoring.service import ScoringService
from meridian_v2.storage.schema import PriceCache
from meridian_v2.watchlist.service import WatchlistService


def test_archived_names_are_not_scored(session):
    watch = WatchlistService(session)
    live = watch.add("RELIANCE", "equity")
    dead = watch.add("INFY", "equity")
    now = datetime.now(UTC).replace(tzinfo=None)
    for symbol, last, prev in (("RELIANCE", 1400.0, 1380.0), ("INFY", 1500.0, 1600.0)):
        session.add(
            PriceCache(
                symbol=symbol,
                contract_label="CONTINUOUS",
                series_kind="CONTINUOUS",
                last=last,
                prev_close=prev,
                as_of=now,
                quality="seed",
                source="test",
            )
        )
    session.flush()
    watch.archive(dead.id)
    session.flush()
    scores = ScoringService(session).score_active()
    assert live.symbol in scores
    assert "INFY" not in scores
