"""Advisor stress stub — not VaR theatre, not an order."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.storage.schema import BookLegRow


@dataclass(frozen=True)
class StressStub:
    shock_pct: float
    assumed_beta: float
    book_notional: float
    estimated_hit: float
    copy: str


def nifty_down_scenario(session: Session, *, shock_pct: float = -5.0, beta: float = 1.0) -> StressStub:
    book = list(session.scalars(select(BookLegRow)))
    notional = sum(abs(row.lots * row.multiplier * row.mark_inr) for row in book)
    hit = notional * beta * (shock_pct / 100.0)
    copy = (
        f"STRESS NOTE — not an order. If the index is {shock_pct:.1f}% and regime → Stress, "
        f"a book notional of ₹{notional:,.0f} at assumed β={beta:.2f} implies about "
        f"₹{hit:,.0f} mark hit (residual haircut not modelled). Review the hedge book?"
    )
    return StressStub(shock_pct=shock_pct, assumed_beta=beta, book_notional=notional, estimated_hit=hit, copy=copy)
