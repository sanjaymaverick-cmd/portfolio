from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.storage.schema import Attribution


class AttributionRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self, symbol: str) -> Attribution | None:
        return self.session.scalar(
            select(Attribution)
            .where(Attribution.symbol == symbol.upper())
            .order_by(Attribution.as_of.desc(), Attribution.id.desc())
        )

    def previous(self, symbol: str) -> Attribution | None:
        latest = self.latest(symbol)
        if latest is None:
            return None
        return self.session.scalar(
            select(Attribution)
            .where(Attribution.symbol == symbol.upper(), Attribution.id < latest.id)
            .order_by(Attribution.as_of.desc(), Attribution.id.desc())
        )

    def record(
        self,
        *,
        symbol: str,
        regime: str | None,
        action: str | None,
        composite: Decimal | None,
        base_value: float,
        engine: str,
        phis: dict[str, float],
        reasoning: str,
        portfolio_note: str,
    ) -> Attribution:
        row = Attribution(
            symbol=symbol.upper(),
            as_of=datetime.now(),
            regime=regime,
            action=action,
            composite=composite,
            base_value=Decimal(str(round(base_value, 4))),
            engine=engine,
            phis=json.dumps(phis),
            reasoning=reasoning,
            portfolio_note=portfolio_note,
        )
        self.session.add(row)
        self.session.flush()
        return row
