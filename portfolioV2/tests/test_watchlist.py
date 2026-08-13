from __future__ import annotations

import pytest

from meridian_v2.watchlist.service import WatchlistError, WatchlistService


def test_add_and_archive_excluded_from_active(session):
    svc = WatchlistService(session)
    item = svc.add("RELIANCE", "equity", "core")
    session.flush()
    assert svc.active_count() == 1
    svc.archive(item.id)
    session.flush()
    assert svc.active_count() == 0
    assert svc.list_items(status="archived")[0].symbol == "RELIANCE"


def test_soft_cap(session, monkeypatch):
    from meridian_v2.config import get_settings

    get_settings().watchlist.active_cap = 2
    svc = WatchlistService(session)
    svc.cap = 2
    svc.add("AAA", "equity")
    svc.add("BBB", "equity")
    session.flush()
    with pytest.raises(WatchlistError, match="soft cap"):
        svc.add("CCC", "equity")
    state = svc.cap_state()
    assert state["at_cap"] is True
    assert state["warn"] is True
    assert state["remaining"] == 0
