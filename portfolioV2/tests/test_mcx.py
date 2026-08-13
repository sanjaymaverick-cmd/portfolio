from __future__ import annotations

from datetime import date, timedelta

from meridian_v2.mcx.roll import ContractSpec, evaluate_continuous, ui_series_label


def test_ui_never_bare_ticker():
    spec = ContractSpec("GOLD", "GOLD26APR", "GOLD26JUN", date(2026, 4, 20))
    label = ui_series_label(spec)
    assert "CONTINUOUS" in label
    assert "GOLD" in label
    assert label != "GOLD"


def test_roll_window_does_not_silently_jump():
    spec = ContractSpec("GOLD", "GOLD26APR", "GOLD26JUN", date.today() + timedelta(days=1))
    mark = evaluate_continuous(spec, near_mark=72000, next_mark=73500, as_of=date.today(), blackout_days=3)
    assert mark.series_kind == "CONTINUOUS"
    assert mark.contract_label == "CONTINUOUS"
    assert mark.quality == "roll_window"
    assert mark.mark == 72000
    assert "next" in mark.note.lower()
    assert "73500" in mark.note
