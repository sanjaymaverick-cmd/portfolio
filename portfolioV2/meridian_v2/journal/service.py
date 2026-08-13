from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.journal.snapshot import capture_desk_state, dumps
from meridian_v2.storage.schema import Fill, IntendedTrade, PriceCache


class JournalService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_intent(
        self,
        *,
        policy_kind: str,
        symbol: str,
        side: str,
        lots: float,
        reason: str,
        regime: str = "",
        event_id: int | None = None,
        contract_label: str = "",
        net_greeks: dict | None = None,
        ref_mid: float | None = None,
        ref_iv: float | None = None,
    ) -> IntendedTrade:
        row = IntendedTrade(
            event_id=event_id,
            policy_kind=policy_kind,
            symbol=symbol.strip().upper(),
            contract_label=contract_label,
            side=side.lower(),
            lots=float(lots),
            reason=reason.strip(),
            regime=regime,
            net_greeks_json=json.dumps(net_greeks or {}),
            ref_mid=ref_mid,
            ref_iv=ref_iv,
            status="open",
            desk_snapshot_json=dumps(capture_desk_state(self.session, symbol)),
            outcome_snapshot_json="{}",
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def add_fill(
        self,
        *,
        contract: str,
        side: str,
        lots: float,
        price: float,
        instrument_type: str,
        intent_id: int | None = None,
        symbol: str = "",
        fees: float = 0.0,
        filled_at: datetime | None = None,
    ) -> Fill:
        if intent_id is not None and self.session.get(IntendedTrade, intent_id) is None:
            raise ValueError("intent_id does not match a journal intent")
        row = Fill(
            intent_id=intent_id,
            filled_at=filled_at or datetime.now(UTC).replace(tzinfo=None),
            contract=contract,
            symbol=symbol.strip().upper(),
            side=side.lower(),
            lots=float(lots),
            price=float(price),
            fees=float(fees),
            instrument_type=instrument_type,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def intents(self, symbol: str | None = None, day: date | None = None) -> list[IntendedTrade]:
        stmt = select(IntendedTrade).order_by(IntendedTrade.created_at.desc())
        if symbol:
            stmt = stmt.where(IntendedTrade.symbol == symbol.upper())
        if day is not None:
            start = datetime.combine(day, time.min)
            stmt = stmt.where(IntendedTrade.created_at >= start, IntendedTrade.created_at < start + timedelta(days=1))
        return list(self.session.scalars(stmt))

    def latest_mark(self, symbol: str) -> PriceCache | None:
        return self.session.scalar(
            select(PriceCache)
            .where(PriceCache.symbol == symbol.upper())
            .order_by(PriceCache.as_of.desc())
        )

    def fills_for(self, intent_id: int) -> list[Fill]:
        return list(
            self.session.scalars(select(Fill).where(Fill.intent_id == intent_id).order_by(Fill.filled_at))
        )

    def capture_outcome(self, intent_id: int) -> IntendedTrade:
        intent = self.session.get(IntendedTrade, intent_id)
        if intent is None:
            raise ValueError("intent not found")
        intent.outcome_snapshot_json = dumps(capture_desk_state(self.session, intent.symbol))
        return intent

    def post_mortems(self) -> list[dict]:
        out: list[dict] = []
        for intent in self.intents():
            fills = self.fills_for(intent.id)
            fill_lots = sum(f.lots if f.side == intent.side else -f.lots for f in fills)
            mark = self.latest_mark(intent.symbol)
            before = json.loads(intent.desk_snapshot_json or "{}")
            after = json.loads(intent.outcome_snapshot_json or "{}")
            out.append(
                {
                    "intent": intent,
                    "fills": fills,
                    "fill_lots": fill_lots,
                    "unfilled": intent.lots - fill_lots,
                    "mark": mark.last if mark else None,
                    "mark_label": mark.contract_label if mark else "",
                    "mark_quality": mark.quality if mark else "",
                    "before": before,
                    "after": after,
                    "score_then": before.get("score"),
                    "score_now": after.get("score"),
                    "regime_then": before.get("regime"),
                    "regime_now": after.get("regime"),
                    "mark_then": before.get("mark"),
                }
            )
        return out
