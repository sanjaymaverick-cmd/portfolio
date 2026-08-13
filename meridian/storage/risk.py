from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meridian.storage.schema import EwmaState, RiskPoint, RiskSnapshot


class RiskRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, symbol: str) -> RiskSnapshot | None:
        return self.session.get(RiskSnapshot, symbol.upper())

    def map_for(self, symbols: list[str]) -> dict[str, RiskSnapshot]:
        wanted = {item.upper() for item in symbols}
        rows = list(self.session.scalars(select(RiskSnapshot)))
        return {row.symbol: row for row in rows if row.symbol in wanted}

    def upsert(self, **payload: object) -> RiskSnapshot:
        symbol = str(payload["symbol"]).upper()
        row = self.get(symbol)
        payload["symbol"] = symbol
        payload["computed_at"] = datetime.now()
        if row:
            for key, value in payload.items():
                setattr(row, key, value)
        else:
            row = RiskSnapshot(**payload)  # type: ignore[arg-type]
            self.session.add(row)
        self.session.flush()
        return row

    def replace_points(self, symbol: str, points: list[RiskPoint]) -> None:
        symbol = symbol.upper()
        self.session.execute(delete(RiskPoint).where(RiskPoint.symbol == symbol))
        for point in points:
            point.symbol = symbol
            self.session.add(point)
        self.session.flush()

    def points(self, symbol: str, limit: int = 260) -> list[RiskPoint]:
        rows = list(
            self.session.scalars(
                select(RiskPoint)
                .where(RiskPoint.symbol == symbol.upper())
                .order_by(RiskPoint.bar_date.desc())
                .limit(limit)
            )
        )
        return list(reversed(rows))


class EwmaRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, symbol: str) -> EwmaState | None:
        return self.session.get(EwmaState, symbol.upper())

    def save(self, symbol: str, var_m: float, var_i: float, cov: float, last_date: datetime | None) -> EwmaState:
        row = self.get(symbol)
        now = datetime.now()
        if row:
            row.var_m = Decimal(str(var_m))
            row.var_i = Decimal(str(var_i))
            row.cov = Decimal(str(cov))
            row.last_date = last_date
            row.updated_at = now
        else:
            row = EwmaState(
                symbol=symbol.upper(),
                var_m=Decimal(str(var_m)),
                var_i=Decimal(str(var_i)),
                cov=Decimal(str(cov)),
                last_date=last_date,
                updated_at=now,
            )
            self.session.add(row)
        self.session.flush()
        return row
