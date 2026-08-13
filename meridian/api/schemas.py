from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    broker: str = "generic"
    client_id: str | None = None


class HoldingIn(BaseModel):
    account_name: str
    symbol: str
    exchange: str = "NSE"
    company_name: str | None = None
    quantity: Decimal
    avg_cost: Decimal
    last_price: Decimal | None = None
    sector: str | None = None
    notes: str | None = None


class HoldingPatch(BaseModel):
    quantity: Decimal | None = None
    avg_cost: Decimal | None = None
    last_price: Decimal | None = None
    notes: str | None = None
    company_name: str | None = None
    sector: str | None = None
