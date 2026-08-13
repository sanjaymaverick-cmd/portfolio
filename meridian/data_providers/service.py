from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from meridian.config import Settings, get_settings
from meridian.data_providers.types import MarketDataProvider, OhlcvBar
from meridian.domain.symbols import yahoo_candidates
from meridian.storage.market import BarRepo, QuoteRepo, SettingRepo
from meridian.storage.schema import Holding, PriceBar
from meridian.storage.repositories import HoldingRepo


INDEX_SPECS = (
    ("NIFTY", "INDEX", "^NSEI"),
    ("INDIAVIX", "INDEX", "^INDIAVIX"),
)


@dataclass
class RefreshResult:
    marked: int = 0
    failed: list[str] = field(default_factory=list)
    skipped: int = 0
    as_of: datetime | None = None
    error: str | None = None


@dataclass
class TapeSnapshot:
    last_run: datetime | None = None
    last_ok: datetime | None = None
    last_error: str | None = None
    stale: bool = True
    nifty_last: Decimal | None = None
    nifty_prev: Decimal | None = None
    vix_last: Decimal | None = None
    vix_prev: Decimal | None = None
    source: str = "yfinance"

    @property
    def nifty_chg(self) -> Decimal | None:
        if self.nifty_last is None or self.nifty_prev in (None, 0):
            return None
        return ((self.nifty_last - self.nifty_prev) / self.nifty_prev) * Decimal("100")

    @property
    def vix_chg(self) -> Decimal | None:
        if self.vix_last is None or self.vix_prev in (None, 0):
            return None
        return ((self.vix_last - self.vix_prev) / self.vix_prev) * Decimal("100")


class PriceService:
    def __init__(
        self,
        session: Session,
        provider: MarketDataProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.provider = provider
        self.quotes = QuoteRepo(session)
        self.bars = BarRepo(session)
        self.settings_repo = SettingRepo(session)
        self.holdings = HoldingRepo(session)

    def snapshot(self) -> TapeSnapshot:
        ttl = timedelta(minutes=self.settings.providers.price_ttl_minutes)
        last_ok = _parse_dt(self.settings_repo.get("tape.last_ok"))
        last_run = _parse_dt(self.settings_repo.get("tape.last_run"))
        nifty = self.quotes.get("NIFTY", "INDEX")
        vix = self.quotes.get("INDIAVIX", "INDEX")
        stale = last_ok is None or (datetime.now() - last_ok) > ttl
        return TapeSnapshot(
            last_run=last_run,
            last_ok=last_ok,
            last_error=self.settings_repo.get("tape.last_error"),
            stale=stale,
            nifty_last=nifty.last_price if nifty else None,
            nifty_prev=nifty.prev_close if nifty else None,
            vix_last=vix.last_price if vix else None,
            vix_prev=vix.prev_close if vix else None,
        )

    def refresh(self, *, force: bool = False, history: bool = True) -> RefreshResult:
        result = RefreshResult()
        self.settings_repo.set("tape.last_run", datetime.now().isoformat(timespec="seconds"))
        provider = self._provider()
        if provider is None:
            result.error = "yfinance is not available"
            self.settings_repo.set("tape.last_error", result.error)
            return result
        if not self.settings.providers.yfinance_enabled:
            result.error = "Tape disabled in config"
            self.settings_repo.set("tape.last_error", result.error)
            return result

        rows = self.holdings.list()
        ttl = timedelta(minutes=self.settings.providers.price_ttl_minutes)
        now = datetime.now()
        work: list[Holding] = []
        for holding in rows:
            quote = self.quotes.get(holding.symbol, holding.exchange)
            fresh = (
                quote is not None
                and quote.fetched_at is not None
                and (now - quote.fetched_at) <= ttl
            )
            if fresh and not force:
                if holding.price_asof is None and quote is not None:
                    self._apply_cached_quote(holding, quote)
                    result.marked += 1
                else:
                    result.skipped += 1
                continue
            work.append(holding)

        period = _period_for_days(self.settings.providers.history_days if history else 10)
        resolved: dict[str, list[OhlcvBar]] = {}
        pending: dict[str, list[Holding]] = {}
        for holding in work:
            for ticker in yahoo_candidates(holding.symbol, holding.exchange, holding.yahoo):
                pending.setdefault(ticker, []).append(holding)

        if pending:
            fetched = provider.history(list(pending), period=period)
            resolved.update(fetched)

        claimed: set[int] = set()
        for holding in work:
            bars: list[OhlcvBar] | None = None
            used: str | None = None
            for ticker in yahoo_candidates(holding.symbol, holding.exchange, holding.yahoo):
                if ticker in resolved:
                    bars = resolved[ticker]
                    used = ticker
                    break
            if not bars or used is None:
                result.failed.append(holding.symbol)
                continue
            self._persist_symbol(holding, used, bars)
            claimed.add(holding.id)
            result.marked += 1

        self._refresh_indexes(provider, period="3mo")
        self.settings_repo.set("tape.last_ok", datetime.now().isoformat(timespec="seconds"))
        if result.failed:
            self.settings_repo.set("tape.last_error", "No tape: " + ", ".join(result.failed[:8]))
        else:
            self.settings_repo.set("tape.last_error", "")
        result.as_of = datetime.now()
        logger.info(
            "tape refresh marked={} skipped={} failed={}",
            result.marked,
            result.skipped,
            len(result.failed),
        )
        return result

    def ensure_history(self, yahoo: str, *, force: bool = False) -> list[PriceBar]:
        min_bars = 80
        last = self.bars.last_date(yahoo)
        count = self.bars.count(yahoo)
        recent = last is not None and (datetime.now() - last) <= timedelta(days=4)
        if not force and count >= min_bars and recent:
            return self.bars.list(yahoo, limit=self.settings.providers.history_days)
        provider = self._provider()
        if provider is None:
            return self.bars.list(yahoo, limit=self.settings.providers.history_days)
        fetched = provider.history([yahoo], period=_period_for_days(self.settings.providers.history_days))
        bars = fetched.get(yahoo, [])
        if bars:
            self._store_bars(yahoo, bars)
        return self.bars.list(yahoo, limit=self.settings.providers.history_days)

    def closes(self, yahoo: str, limit: int = 30) -> list[float]:
        return [float(bar.close) for bar in self.bars.list(yahoo, limit=limit)]

    def _apply_cached_quote(self, holding: Holding, quote) -> None:  # noqa: ANN001
        holding.last_price = quote.last_price
        holding.prev_close = quote.prev_close
        holding.price_asof = quote.as_of
        holding.yahoo = quote.yahoo

    def _persist_symbol(self, holding: Holding, yahoo: str, bars: list[OhlcvBar]) -> None:
        last = bars[-1]
        prev = bars[-2].close if len(bars) >= 2 else None
        as_of = datetime.combine(last.bar_date, datetime.min.time())
        holding.last_price = last.close
        holding.prev_close = prev
        holding.price_asof = as_of
        holding.yahoo = yahoo
        self.quotes.upsert(
            symbol=holding.symbol,
            exchange=holding.exchange,
            yahoo=yahoo,
            last_price=last.close,
            prev_close=prev,
            as_of=as_of,
        )
        self._store_bars(yahoo, bars)

    def _refresh_indexes(self, provider: MarketDataProvider, period: str) -> None:
        fetched = provider.history([spec[2] for spec in INDEX_SPECS], period=period)
        for symbol, exchange, yahoo in INDEX_SPECS:
            bars = fetched.get(yahoo)
            if not bars:
                continue
            last = bars[-1]
            prev = bars[-2].close if len(bars) >= 2 else None
            as_of = datetime.combine(last.bar_date, datetime.min.time())
            self.quotes.upsert(
                symbol=symbol,
                exchange=exchange,
                yahoo=yahoo,
                last_price=last.close,
                prev_close=prev,
                as_of=as_of,
            )
            self._store_bars(yahoo, bars)

    def _store_bars(self, yahoo: str, bars: list[OhlcvBar]) -> None:
        rows = [
            PriceBar(
                yahoo=yahoo,
                bar_date=datetime.combine(bar.bar_date, datetime.min.time()),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in bars
        ]
        self.bars.replace_many(yahoo, rows)

    def _provider(self) -> MarketDataProvider | None:
        if self.provider is not None:
            return self.provider
        if not self.settings.providers.yfinance_enabled:
            return None
        try:
            from meridian.data_providers.yahoo import YahooProvider

            return YahooProvider()
        except Exception as exc:  # noqa: BLE001
            logger.warning("price provider unavailable: {}", exc)
            return None


def day_pnl(quantity: Decimal, last: Decimal | None, prev: Decimal | None) -> Decimal | None:
    if last is None or prev is None:
        return None
    return quantity * (last - prev)


def day_pnl_pct(last: Decimal | None, prev: Decimal | None) -> Decimal | None:
    if last is None or prev is None or prev == 0:
        return None
    return (last - prev) / prev * Decimal("100")


def _period_for_days(days: int) -> str:
    if days <= 7:
        return "10d"
    if days <= 40:
        return "3mo"
    if days <= 100:
        return "6mo"
    if days <= 280:
        return "1y"
    return "2y"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
