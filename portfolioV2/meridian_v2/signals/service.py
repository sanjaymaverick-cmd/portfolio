from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.config import get_settings
from meridian_v2.domain.models import AckAction, PolicyKind, SignalStatus
from meridian_v2.storage.schema import DeskEvent


class SignalService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def pending(self) -> list[DeskEvent]:
        now = datetime.now(UTC).replace(tzinfo=None)
        rows = list(
            self.session.scalars(
                select(DeskEvent)
                .where(DeskEvent.status.in_([SignalStatus.PENDING.value, SignalStatus.SNOOZED.value]))
                .order_by(DeskEvent.created_at.desc())
            )
        )
        live: list[DeskEvent] = []
        for row in rows:
            if row.status == SignalStatus.SNOOZED.value and row.snooze_until and row.snooze_until > now:
                continue
            if row.status == SignalStatus.SNOOZED.value:
                row.status = SignalStatus.PENDING.value
            live.append(row)
        return live

    def enqueue(
        self,
        *,
        policy_kind: str,
        symbol: str,
        copy_review: str,
        reason: str,
        regime: str,
        rule_name: str = "",
        strength: float = 0.0,
        contract_label: str = "",
        payload: dict | None = None,
        status: str = SignalStatus.PENDING.value,
    ) -> DeskEvent:
        existing = self.session.scalar(
            select(DeskEvent).where(
                DeskEvent.policy_kind == policy_kind,
                DeskEvent.symbol == symbol,
                DeskEvent.status == SignalStatus.PENDING.value,
                DeskEvent.rule_name == rule_name,
            )
        )
        if existing:
            existing.copy_review = copy_review
            existing.reason = reason
            existing.regime = regime
            existing.strength = strength
            existing.payload_json = json.dumps(payload or {})
            return existing
        event = DeskEvent(
            policy_kind=policy_kind,
            symbol=symbol,
            contract_label=contract_label,
            rule_name=rule_name,
            strength=strength,
            reason=reason,
            copy_review=copy_review,
            regime=regime,
            payload_json=json.dumps(payload or {}),
            status=status,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self.session.add(event)
        self.session.flush()
        return event

    def ack(self, event_id: int, action: str) -> DeskEvent:
        event = self.session.get(DeskEvent, event_id)
        if event is None:
            raise ValueError("event not found")
        now = datetime.now(UTC).replace(tzinfo=None)
        if action == AckAction.ACCEPT.value:
            event.status = SignalStatus.ACCEPTED.value
            event.acked_at = now
        elif action == AckAction.DISMISS.value:
            event.status = SignalStatus.DISMISSED.value
            event.acked_at = now
        elif action == AckAction.SNOOZE.value:
            hours = get_settings().alerts.snooze_hours
            event.status = SignalStatus.SNOOZED.value
            event.snooze_until = now + timedelta(hours=hours)
            event.acked_at = now
        else:
            raise ValueError(f"unknown ack action: {action}")
        return event

    def by_policy(self, policy_kind: str) -> list[DeskEvent]:
        return [e for e in self.pending() if e.policy_kind == policy_kind]

    def all_recent(self, limit: int = 50) -> list[DeskEvent]:
        return list(
            self.session.scalars(
                select(DeskEvent).order_by(DeskEvent.created_at.desc()).limit(limit)
            )
        )
