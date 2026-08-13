from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field

from meridian.domain.money import safe_div


class AccountView(BaseModel):
    id: int
    name: str
    broker: str
    client_id: str | None = None
    is_active: bool = True
    holding_count: int = 0
    market_value: Decimal = Decimal("0")


class HoldingView(BaseModel):
    id: int
    account_id: int
    account_name: str
    broker: str
    symbol: str
    exchange: str
    yahoo: str
    isin: str | None = None
    company_name: str
    sector: str
    mcap: str = "Unclassified"
    quantity: Decimal
    avg_cost: Decimal
    last_price: Decimal | None = None
    prev_close: Decimal | None = None
    price_asof: datetime | None = None
    source: str = "import"
    notes: str | None = None
    updated_at: datetime | None = None
    recommendation: str = "—"
    score: Decimal | None = None
    quality: Decimal | None = None
    valuation: Decimal | None = None
    technical: Decimal | None = None
    rho: Decimal | None = None
    beta: Decimal | None = None
    beta_ols: Decimal | None = None
    beta_ewma: Decimal | None = None
    rsi: Decimal | None = None
    spark: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def invested(self) -> Decimal:
        return self.quantity * self.avg_cost

    @computed_field  # type: ignore[prop-decorator]
    @property
    def market_value(self) -> Decimal | None:
        if self.last_price is None:
            return None
        return self.quantity * self.last_price

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pnl(self) -> Decimal | None:
        mv = self.market_value
        if mv is None:
            return None
        return mv - self.invested

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pnl_pct(self) -> Decimal | None:
        return safe_div(self.pnl, self.invested) * Decimal("100") if self.pnl is not None else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def day_pnl(self) -> Decimal | None:
        if self.last_price is None or self.prev_close is None:
            return None
        return self.quantity * (self.last_price - self.prev_close)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def day_pnl_pct(self) -> Decimal | None:
        if self.last_price is None or self.prev_close in (None, 0):
            return None
        return ((self.last_price - self.prev_close) / self.prev_close) * Decimal("100")


class BookSummary(BaseModel):
    market_value: Decimal = Decimal("0")
    invested: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    pnl_pct: Decimal | None = None
    names: int = 0
    accounts: int = 0
    day_pnl: Decimal | None = None
    day_pnl_pct: Decimal | None = None
    day_undefined: bool = True
    tape_asof: datetime | None = None
    sector_weights: list[tuple[str, Decimal]] = Field(default_factory=list)
    mcap_weights: list[tuple[str, Decimal]] = Field(default_factory=list)
    top_weight: Decimal | None = None
    top_symbol: str | None = None


class MappedRow(BaseModel):
    symbol: str
    exchange: str
    company_name: str | None = None
    isin: str | None = None
    quantity: Decimal
    avg_cost: Decimal
    last_price: Decimal | None = None
    sector: str | None = None
    raw: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class ImportPreview(BaseModel):
    broker: str
    filename: str
    headers: list[str]
    mapping: dict[str, str]
    rows: list[MappedRow]
    accepted: int = 0
    rejected: int = 0
