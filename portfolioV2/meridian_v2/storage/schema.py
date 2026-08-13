from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WatchItem(Base):
    __tablename__ = "watch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    notes: Mapped[str] = mapped_column(Text, default="")
    stance: Mapped[str] = mapped_column(String(16), default="")
    sector: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class McxContract(Base):
    __tablename__ = "mcx_contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    near_label: Mapped[str] = mapped_column(String(64), default="")
    next_label: Mapped[str] = mapped_column(String(64), default="")
    roll_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    series_kind: Mapped[str] = mapped_column(String(16), default="CONTINUOUS")
    notes: Mapped[str] = mapped_column(Text, default="")


class PriceCache(Base):
    __tablename__ = "price_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    contract_label: Mapped[str] = mapped_column(String(64), default="CONTINUOUS")
    series_kind: Mapped[str] = mapped_column(String(16), default="CONTINUOUS")
    last: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quality: Mapped[str] = mapped_column(String(24), default="ok")
    source: Mapped[str] = mapped_column(String(32), default="stub")
    sma20: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma50: Mapped[float | None] = mapped_column(Float, nullable=True)
    weekly_last: Mapped[float | None] = mapped_column(Float, nullable=True)
    weekly_sma: Mapped[float | None] = mapped_column(Float, nullable=True)
    high20: Mapped[float | None] = mapped_column(Float, nullable=True)
    low20: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_volume: Mapped[float | None] = mapped_column(Float, nullable=True)


class BookLegRow(Base):
    __tablename__ = "book_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leg_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    lots: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    mark_inr: Mapped[float] = mapped_column(Float, nullable=False)
    contract_label: Mapped[str] = mapped_column(String(64), default="CONTINUOUS")
    delta: Mapped[float] = mapped_column(Float, default=1.0)
    gamma: Mapped[float] = mapped_column(Float, default=0.0)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)


class HedgeLegRow(Base):
    __tablename__ = "hedge_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leg_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    lots: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    mark_inr: Mapped[float] = mapped_column(Float, nullable=False)
    contract_label: Mapped[str] = mapped_column(String(64), default="")
    delta: Mapped[float] = mapped_column(Float, default=1.0)
    gamma: Mapped[float] = mapped_column(Float, default=0.0)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)


class OptionLegRow(Base):
    __tablename__ = "option_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leg_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    contract_label: Mapped[str] = mapped_column(String(64), default="")
    lots: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    mark_inr: Mapped[float] = mapped_column(Float, default=0.0)
    delta: Mapped[float] = mapped_column(Float, default=0.5)
    gamma: Mapped[float] = mapped_column(Float, default=0.0)
    vega_per_lot: Mapped[float] = mapped_column(Float, default=0.0)
    theta_per_lot: Mapped[float] = mapped_column(Float, default=0.0)
    iv: Mapped[float | None] = mapped_column(Float, nullable=True)
    greeks_as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stale: Mapped[int] = mapped_column(Integer, default=0)


class DeskEvent(Base):
    """Unified ack queue for signals and policy reviews."""

    __tablename__ = "desk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    contract_label: Mapped[str] = mapped_column(String(64), default="")
    rule_name: Mapped[str] = mapped_column(String(64), default="")
    strength: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    copy_review: Mapped[str] = mapped_column(Text, default="")
    regime: Mapped[str] = mapped_column(String(16), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class IntendedTrade(Base):
    __tablename__ = "intended_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("desk_events.id"), nullable=True)
    policy_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_label: Mapped[str] = mapped_column(String(64), default="")
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    lots: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    regime: Mapped[str] = mapped_column(String(16), default="")
    net_greeks_json: Mapped[str] = mapped_column(Text, default="{}")
    ref_mid: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_iv: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    desk_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    outcome_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent_id: Mapped[int | None] = mapped_column(ForeignKey("intended_trades.id"), nullable=True)
    filled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    contract: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), default="")
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    lots: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)


class FxMark(Base):
    __tablename__ = "fx_marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pair: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    last: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quality: Mapped[str] = mapped_column(String(24), default="ok")
    source: Mapped[str] = mapped_column(String(32), default="stub")


class RegimeState(Base):
    __tablename__ = "regime_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class WatchCatalyst(Base):
    __tablename__ = "watch_catalysts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watch_items.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    level: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class FactorScore(Base):
    __tablename__ = "factor_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    technical: Mapped[float | None] = mapped_column(Float, nullable=True)
    tape: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime_fit: Mapped[float | None] = mapped_column(Float, nullable=True)
    news: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite: Mapped[float | None] = mapped_column(Float, nullable=True)
    stance: Mapped[str] = mapped_column(String(16), default="")
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AlertPolicy(Base):
    __tablename__ = "alert_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), default="*")
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str] = mapped_column(Text, default="")


class NewsStub(Base):
    __tablename__ = "news_stubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[float] = mapped_column(Float, default=0.0)
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(64), nullable=False)
    bars: Mapped[int] = mapped_column(Integer, default=0)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Cooldown(Base):
    __tablename__ = "cooldowns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    last_prompt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
