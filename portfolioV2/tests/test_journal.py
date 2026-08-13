from __future__ import annotations

import pytest

from meridian_v2.journal.service import JournalService


def test_fill_prefers_valid_intent(session):
    svc = JournalService(session)
    intent = svc.add_intent(
        policy_kind="inventory_hedge",
        symbol="GOLD",
        side="sell",
        lots=1,
        reason="Hedge review accepted",
        regime="Elevated",
        contract_label="GOLD26APR",
    )
    session.flush()
    fill = svc.add_fill(
        contract="GOLD26APR",
        side="sell",
        lots=1,
        price=72100,
        instrument_type="future",
        intent_id=intent.id,
        symbol="GOLD",
    )
    session.flush()
    rows = svc.post_mortems()
    assert rows[0]["fills"][0].id == fill.id
    assert rows[0]["unfilled"] == 0

    with pytest.raises(ValueError, match="intent_id"):
        svc.add_fill(
            contract="GOLD26APR",
            side="sell",
            lots=1,
            price=1,
            instrument_type="future",
            intent_id=9999,
        )


def test_list_by_symbol(session):
    svc = JournalService(session)
    svc.add_intent(policy_kind="vol_harvest", symbol="GOLD", side="sell", lots=1, reason="d")
    svc.add_intent(policy_kind="signal", symbol="TCS", side="buy", lots=10, reason="e")
    session.flush()
    assert len(svc.intents("GOLD")) == 1


def test_list_by_day(session):
    from datetime import date

    svc = JournalService(session)
    svc.add_intent(policy_kind="signal", symbol="GOLD", side="buy", lots=1, reason="today")
    session.flush()
    assert len(svc.intents(day=date.today())) == 1
    assert svc.intents(day=date(1999, 1, 1)) == []
