from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    broker: Mapped[str] = mapped_column(String(40), default="generic")
    client_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    holdings: Mapped[list[Holding]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("account_id", "symbol", "exchange", name="uq_holding_book"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(8), default="NSE")
    yahoo: Mapped[str] = mapped_column(String(40))
    isin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    company_name: Mapped[str] = mapped_column(String(160))
    sector: Mapped[str] = mapped_column(String(64), default="Unclassified")
    mcap: Mapped[str] = mapped_column(String(24), default="Unclassified")
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    price_asof: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="import")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    account: Mapped[Account] = relationship(back_populates="holdings")


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    broker: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(260))
    status: Mapped[str] = mapped_column(String(24), default="previewed")
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_quote_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(8), default="NSE")
    yahoo: Mapped[str] = mapped_column(String(40), index=True)
    last_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    source: Mapped[str] = mapped_column(String(24), default="yfinance")


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("yahoo", "bar_date", name="uq_bar_yahoo_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    yahoo: Mapped[str] = mapped_column(String(40), index=True)
    bar_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)


class Fundamental(Base):
    __tablename__ = "fundamentals"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(24), default="screener")
    screener_url: Mapped[str | None] = mapped_column(String(240), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(80), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(80), nullable=True)
    market_cap_cr: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    pe: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    book_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    pb: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    roce: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    roe: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    roe_5y: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    opm: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    opm_5y_mean: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    opm_5y_std: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    cfo_to_op: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ev_ebitda: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    sales_cagr_3y: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    sales_cagr_5y: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    profit_cagr_3y: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    profit_cagr_5y: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    promoter_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    promoter_pledge: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    promoter_pledge_prev: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    fii_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    dii_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    fii_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    dii_delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    analysis_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FactorScore(Base):
    __tablename__ = "factor_scores"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    quality: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    valuation: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    technical: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    ownership: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    sentiment: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    composite: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    quality_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    valuation_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ownership_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(String(24), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    source: Mapped[str] = mapped_column(String(24), default="screener")


class Attribution(Base):
    __tablename__ = "attributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    regime: Mapped[str | None] = mapped_column(String(16), nullable=True)
    action: Mapped[str | None] = mapped_column(String(24), nullable=True)
    composite: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    base_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    engine: Mapped[str] = mapped_column(String(24), default="linear")
    phis: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    portfolio_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    yahoo: Mapped[str] = mapped_column(String(40))
    rho: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    beta_ols: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    beta_ewma: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    beta_shrunk: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    rsi: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    sma20: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    sma50: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    sma200: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    rs_nifty: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    volume_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    last_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    window: Mapped[int] = mapped_column(Integer, default=60)
    as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RiskPoint(Base):
    __tablename__ = "risk_points"
    __table_args__ = (UniqueConstraint("symbol", "bar_date", name="uq_risk_point"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    bar_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    rho: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    beta_ewma: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)


class EwmaState(Base):
    __tablename__ = "ewma_state"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    var_m: Mapped[Decimal] = mapped_column(Numeric(18, 12))
    var_i: Mapped[Decimal] = mapped_column(Numeric(18, 12))
    cov: Mapped[Decimal] = mapped_column(Numeric(18, 12))
    last_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FilterState(Base):
    __tablename__ = "filter_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RegimeSnapshot(Base):
    __tablename__ = "regime_snapshots"

    as_of: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    label: Mapped[str] = mapped_column(String(16))
    soft_calm: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    soft_elevated: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    soft_stress: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    vix: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ewma_vol_ann: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    kalman_trend_z: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    nifty_vs_sma50: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    vix_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DailyPerformance(Base):
    __tablename__ = "daily_performance"
    __table_args__ = (UniqueConstraint("as_of", "symbol", name="uq_daily_perf"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    company_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    day_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    day_pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    contribution: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    why: Mapped[str | None] = mapped_column(String(40), nullable=True)


class DailyNews(Base):
    __tablename__ = "daily_news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(400))
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="rss")
    published: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sentiment: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    aspect: Mapped[str] = mapped_column(String(24), default="Other")
    rank: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    is_filing: Mapped[bool] = mapped_column(Boolean, default=False)
    kept: Mapped[bool] = mapped_column(Boolean, default=False)


class DailyImpact(Base):
    __tablename__ = "daily_attribution"
    __table_args__ = (UniqueConstraint("as_of", "symbol", name="uq_daily_impact"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    engine: Mapped[str] = mapped_column(String(24), default="rules")
    takeaway: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    positives: Mapped[str | None] = mapped_column(Text, nullable=True)
    negatives: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)


class AlertEvent(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("as_of", "kind", "symbol", name="uq_alert_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(12), default="watch")
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    shap_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WatchItem(Base):
    __tablename__ = "watchlist"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    company_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
