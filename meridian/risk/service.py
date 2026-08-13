from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from meridian.config import Settings, get_settings
from meridian.risk.math import (
    AlignedSeries,
    Ewma,
    align_closes,
    corr_beta,
    ewma_path,
    relative_strength,
    rolling_corr_beta,
    rsi,
    seed_ewma,
    shrink_beta,
    sma,
    volume_ratio,
)
from meridian.scoring.technical import score_technical
from meridian.storage.fundamentals import FactorRepo
from meridian.storage.market import BarRepo, SettingRepo
from meridian.storage.repositories import HoldingRepo
from meridian.storage.risk import EwmaRepo, RiskRepo
from meridian.storage.schema import PriceBar, RiskPoint

BOOK = "PORTFOLIO"


@dataclass
class RiskRefresh:
    marked: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    error: str | None = None
    nifty: str | None = None


class RiskService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.bars = BarRepo(session)
        self.holdings = HoldingRepo(session)
        self.risk = RiskRepo(session)
        self.ewma = EwmaRepo(session)
        self.factors = FactorRepo(session)
        self.settings_repo = SettingRepo(session)

    def compute(self, *, force: bool = False, symbol: str | None = None) -> RiskRefresh:
        result = RiskRefresh()
        self.settings_repo.set("risk.last_run", datetime.now().isoformat(timespec="seconds"))
        nifty_bars, nifty_yahoo = self._nifty_bars()
        result.nifty = nifty_yahoo
        if not nifty_bars:
            result.error = "Nifty history missing — run python -m meridian prices first"
            self.settings_repo.set("risk.last_error", result.error)
            return result

        window = self.settings.market.correlation_window
        lam = self.settings.market.ewma_lambda
        shrink = self.settings.market.beta_shrinkage
        rsi_n = self.settings.market.rsi_period

        rows = self.holdings.list()
        if symbol:
            rows = [row for row in rows if row.symbol.upper() == symbol.upper()]
        seen: dict[str, tuple[str, list[PriceBar]]] = {}
        for holding in rows:
            key = holding.symbol.upper()
            if key in seen:
                continue
            seen[key] = (holding.yahoo, self.bars.list(holding.yahoo, limit=self.settings.providers.history_days))

        book_returns: dict[datetime, list[tuple[float, float]]] = {}
        weights = self._weights(rows)

        for key, (yahoo, bars) in seen.items():
            aligned = align_closes(bars, nifty_bars)
            if aligned is None or len(aligned.asset) < 10:
                result.failed.append(key)
                continue
            snap = self._persist_name(
                key,
                yahoo,
                aligned,
                window=window,
                lam=lam,
                shrink=shrink,
                rsi_n=rsi_n,
                force=force,
            )
            if snap is None:
                result.skipped += 1
                continue
            result.marked += 1
            weight = weights.get(key, 0.0)
            if weight:
                for date, ret in zip(aligned.dates[1:], aligned.asset, strict=False):
                    book_returns.setdefault(date, []).append((weight, ret))

        if book_returns and not symbol:
            self._persist_book(book_returns, nifty_bars, window=window, lam=lam, shrink=shrink)

        if result.failed:
            self.settings_repo.set("risk.last_error", "Thin tape: " + ", ".join(result.failed[:8]))
        else:
            self.settings_repo.set("risk.last_error", "")
        if result.marked:
            self.settings_repo.set("risk.last_ok", datetime.now().isoformat(timespec="seconds"))
        logger.info("risk marked={} failed={} nifty={}", result.marked, len(result.failed), nifty_yahoo)
        return result

    def book_snapshot(self):
        return self.risk.get(BOOK)

    def _persist_name(
        self,
        symbol: str,
        yahoo: str,
        aligned: AlignedSeries,
        *,
        window: int,
        lam: float,
        shrink: float,
        rsi_n: int,
        force: bool,
    ):
        last_date = aligned.dates[-1]
        existing = self.risk.get(symbol)
        if (
            not force
            and existing
            and existing.as_of
            and existing.as_of.date() == last_date.date()
        ):
            return None

        rhos, betas = rolling_corr_beta(aligned.asset, aligned.market, window)
        ewma_betas = ewma_path(aligned.asset, aligned.market, lam)
        state = self._advance_ewma(symbol, aligned, lam, force=force)
        rho = rhos[-1] if rhos else None
        beta_ols = betas[-1] if betas else None
        beta_ewma = state.beta if state else (ewma_betas[-1] if ewma_betas else None)
        last = aligned.asset_px[-1]
        sma20 = sma(aligned.asset_px, 20)
        sma50 = sma(aligned.asset_px, 50)
        sma200 = sma(aligned.asset_px, 200)
        rsi_v = rsi(aligned.asset_px, rsi_n)
        rs = relative_strength(aligned.asset_px, aligned.market_px, window)
        vol = volume_ratio(aligned.volume)
        technical, parts = score_technical(
            last=last,
            sma20=sma20,
            sma50=sma50,
            sma200=sma200,
            rsi=rsi_v,
            rs_nifty=rs,
            volume_ratio=vol,
        )
        self.risk.upsert(
            symbol=symbol,
            yahoo=yahoo,
            rho=_dec(rho),
            beta_ols=_dec(beta_ols),
            beta_ewma=_dec(beta_ewma),
            beta_shrunk=_dec(shrink_beta(beta_ewma, shrink)),
            rsi=_dec(rsi_v),
            sma20=_dec(sma20),
            sma50=_dec(sma50),
            sma200=_dec(sma200),
            rs_nifty=_dec(None if rs is None else rs * 100),
            volume_ratio=_dec(vol),
            last_close=_dec(last),
            window=window,
            as_of=last_date,
        )
        points = []
        for date, rho_i, beta_i in zip(aligned.dates[1:], rhos, ewma_betas, strict=False):
            if rho_i is None and beta_i is None:
                continue
            points.append(RiskPoint(symbol=symbol, bar_date=date, rho=_dec(rho_i), beta_ewma=_dec(beta_i)))
        self.risk.replace_points(symbol, points[-180:])
        self.factors.update_technical(
            symbol,
            technical=technical,
            technical_detail=json.dumps({k: None if v is None else float(v) for k, v in parts.items()}),
            source="tape",
        )
        return True

    def _advance_ewma(self, symbol: str, aligned: AlignedSeries, lam: float, *, force: bool) -> Ewma | None:
        stored = None if force else self.ewma.get(symbol)
        if stored and stored.last_date:
            last = stored.last_date.date() if hasattr(stored.last_date, "date") else stored.last_date
            state = Ewma(
                var_m=float(stored.var_m),
                var_i=float(stored.var_i),
                cov=float(stored.cov),
                lam=lam,
            )
            applied = False
            for date, r_i, r_m in zip(aligned.dates[1:], aligned.asset, aligned.market, strict=False):
                day = date.date() if hasattr(date, "date") else date
                if day <= last:
                    continue
                state.update(r_i, r_m)
                applied = True
            if applied or not force:
                self.ewma.save(symbol, state.var_m, state.var_i, state.cov, aligned.dates[-1])
                return state
        state = seed_ewma(aligned.asset, aligned.market, lam)
        self.ewma.save(symbol, state.var_m, state.var_i, state.cov, aligned.dates[-1])
        return state

    def _persist_book(
        self,
        book_returns: dict[datetime, list[tuple[float, float]]],
        nifty_bars: list[PriceBar],
        *,
        window: int,
        lam: float,
        shrink: float,
    ) -> None:
        mkt = {_day(bar.bar_date): float(bar.close) for bar in nifty_bars}
        dates = sorted(d for d in book_returns if _day(d) in mkt or d in mkt)
        if len(dates) < 15:
            return
        mkt_px = []
        port = []
        use_dates = []
        prev_m = None
        for date in dates:
            key = _day(date)
            px = mkt.get(key)
            if px is None:
                continue
            pairs = book_returns[date]
            mass = sum(w for w, _ in pairs)
            if mass <= 0:
                continue
            rp = sum(w * r for w, r in pairs) / mass
            if prev_m is not None:
                port.append(rp)
                mkt_px.append((px / prev_m) - 1.0 if prev_m else 0.0)
                use_dates.append(date)
            prev_m = px
        if len(port) < 10:
            return
        rho, beta = corr_beta(port[-window:], mkt_px[-window:])
        path = ewma_path(port, mkt_px, lam)
        rhos, _ = rolling_corr_beta(port, mkt_px, window)
        beta_e = path[-1] if path else None
        self.risk.upsert(
            symbol=BOOK,
            yahoo=self.settings.market.nifty_ticker,
            rho=_dec(rho),
            beta_ols=_dec(beta),
            beta_ewma=_dec(beta_e),
            beta_shrunk=_dec(shrink_beta(beta_e, shrink)),
            window=window,
            as_of=use_dates[-1] if use_dates else None,
        )
        points = [
            RiskPoint(symbol=BOOK, bar_date=date, rho=_dec(rho_i), beta_ewma=_dec(beta_i))
            for date, rho_i, beta_i in zip(use_dates, rhos, path, strict=False)
            if rho_i is not None or beta_i is not None
        ]
        self.risk.replace_points(BOOK, points[-180:])

    def _nifty_bars(self) -> tuple[list[PriceBar], str | None]:
        primary = self.settings.market.nifty_ticker
        fallback = self.settings.market.nifty_fallback
        for ticker in (primary, fallback):
            bars = self.bars.list(ticker, limit=self.settings.providers.history_days)
            if len(bars) >= 40:
                return bars, ticker
        # explicit job may hydrate once
        try:
            from meridian.data_providers.service import PriceService

            PriceService(self.session).ensure_history(primary)
            bars = self.bars.list(primary, limit=self.settings.providers.history_days)
            if len(bars) >= 40:
                return bars, primary
            if fallback:
                PriceService(self.session).ensure_history(fallback)
                bars = self.bars.list(fallback, limit=self.settings.providers.history_days)
                if len(bars) >= 40:
                    return bars, fallback
        except Exception as exc:  # noqa: BLE001
            logger.warning("nifty hydrate failed: {}", exc)
        return [], None

    def _weights(self, holdings) -> dict[str, float]:  # noqa: ANN001
        totals: dict[str, float] = {}
        for holding in holdings:
            if holding.last_price is None:
                continue
            totals[holding.symbol.upper()] = totals.get(holding.symbol.upper(), 0.0) + float(
                holding.quantity * holding.last_price
            )
        mass = sum(totals.values()) or 1.0
        return {key: value / mass for key, value in totals.items()}


def _dec(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(value, 6)))


def _day(value: datetime) -> datetime:
    if hasattr(value, "date"):
        return datetime.combine(value.date(), datetime.min.time())
    return value
