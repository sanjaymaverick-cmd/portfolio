from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.config import get_settings
from meridian_v2.mcx.roll import ContractSpec, ContinuousMark, evaluate_continuous
from meridian_v2.storage.schema import McxContract, PriceCache


class McxService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def specs(self) -> list[ContractSpec]:
        rows = list(self.session.scalars(select(McxContract).order_by(McxContract.symbol_key)))
        return [
            ContractSpec(
                symbol_key=row.symbol_key,
                near_label=row.near_label,
                next_label=row.next_label,
                roll_date=row.roll_date,
                multiplier=row.multiplier,
                series_kind=row.series_kind,
                notes=row.notes,
            )
            for row in rows
        ]

    def spec(self, symbol_key: str) -> ContractSpec | None:
        row = self.session.scalar(select(McxContract).where(McxContract.symbol_key == symbol_key))
        if row is None:
            return None
        return ContractSpec(
            symbol_key=row.symbol_key,
            near_label=row.near_label,
            next_label=row.next_label,
            roll_date=row.roll_date,
            multiplier=row.multiplier,
            series_kind=row.series_kind,
            notes=row.notes,
        )

    def marks(self, as_of: date | None = None) -> list[ContinuousMark]:
        as_of = as_of or date.today()
        blackout = get_settings().hedge.roll_blackout_days
        out: list[ContinuousMark] = []
        for spec in self.specs():
            near = self._price(spec.symbol_key, spec.near_label or "CONTINUOUS")
            nxt = self._price(spec.symbol_key, spec.next_label or "NEXT")
            out.append(
                evaluate_continuous(
                    spec,
                    near_mark=near,
                    next_mark=nxt,
                    as_of=as_of,
                    blackout_days=blackout,
                )
            )
        return out

    def _price(self, symbol: str, contract_label: str) -> float | None:
        row = self.session.scalar(
            select(PriceCache).where(
                PriceCache.symbol == symbol,
                PriceCache.contract_label == contract_label,
            )
        )
        if row is None:
            row = self.session.scalar(
                select(PriceCache).where(
                    PriceCache.symbol == symbol,
                    PriceCache.contract_label == "CONTINUOUS",
                )
            )
        return row.last if row else None
