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
