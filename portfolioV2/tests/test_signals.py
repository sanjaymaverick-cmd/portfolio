from __future__ import annotations

from meridian_v2.domain.models import AckAction, SignalStatus
from meridian_v2.signals.service import SignalService


def test_ack_transitions_and_snooze(session):
    svc = SignalService(session)
    ev = svc.enqueue(
        policy_kind="signal",
        symbol="RELIANCE",
        copy_review="Review the name.",
        reason="test",
        regime="Elevated",
        rule_name="score_threshold_regime",
    )
    session.flush()
    assert ev.status == SignalStatus.PENDING.value
    svc.ack(ev.id, AckAction.SNOOZE.value)
    session.flush()
    assert ev.status == SignalStatus.SNOOZED.value
    assert ev.snooze_until is not None
    assert ev.id not in {e.id for e in svc.pending()}

    ev2 = svc.enqueue(
        policy_kind="signal",
        symbol="TCS",
        copy_review="Review TCS.",
        reason="test",
        regime="Calm",
        rule_name="trend_ma_regime",
    )
    session.flush()
    svc.ack(ev2.id, AckAction.ACCEPT.value)
    assert ev2.status == SignalStatus.ACCEPTED.value
    svc.ack(
        svc.enqueue(
            policy_kind="signal",
            symbol="INFY",
            copy_review="x",
            reason="x",
            regime="Calm",
            rule_name="x",
        ).id,
        AckAction.DISMISS.value,
    )
    session.flush()
