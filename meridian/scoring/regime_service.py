from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from meridian.config import RegimeCfg, Settings, get_settings
from meridian.risk.ewma_variance import EwmaVariance
from meridian.risk.kalman_trend import KalmanTrend
from meridian.risk.math import sma
from meridian.scoring.regime import RegimeInputs, decide
from meridian.storage.market import BarRepo, QuoteRepo
from meridian.storage.regime import FilterStateRepo, RegimeRepo, dec
from meridian.storage.schema import PriceBar, RegimeSnapshot

EWMA_KEY = "regime.ewma_nifty"
KALMAN_KEY = "regime.kalman_nifty"
DETECTOR_KEY = "regime.detector"


@dataclass
class RegimeJobResult:
    label: str | None = None
    as_of: datetime | None = None
    reason: str | None = None
    error: str | None = None
    vix_source: str | None = None


class RegimeInputService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.bars = BarRepo(session)
        self.quotes = QuoteRepo(session)
        self.filters = FilterStateRepo(session)
        self.regimes = RegimeRepo(session)

    def build_regime_inputs(
        self,
        as_of: datetime | date | None = None,
        *,
        persist: bool = True,
        hydrate: bool = False,
    ) -> RegimeInputs:
        cfg = self.settings.regime
        when = _as_dt(as_of or datetime.now())
        if hydrate:
            self._hydrate(cfg.history_days)
        nifty_yahoo = self._nifty_yahoo()
        closes, dates = self._closes(nifty_yahoo, when, cfg.history_days)
        if len(closes) < 10:
            raise ValueError("Nifty history missing — run python -m meridian prices first")

        returns = [
            (closes[i] / closes[i - 1] - 1.0) if closes[i - 1] else 0.0 for i in range(1, len(closes))
        ]
        ewma = EwmaVariance(lam=self.settings.market.ewma_lambda)
        ewma.update_series(returns)
        kalman = KalmanTrend(
            q_level=cfg.kalman.q_level,
            q_trend=cfg.kalman.q_trend,
            r=cfg.kalman.r,
        )
        kalman.update_series(closes)
        sma_n = sma(closes, cfg.sma_window)
        vs_sma = None if sma_n in (None, 0) else (closes[-1] / sma_n - 1.0) * 100.0
        vix, vix_source, notes = self._resolve_vix(when, ewma.vol_ann)
        if persist:
            self.filters.set(EWMA_KEY, {**ewma.to_dict(), "as_of": when.isoformat()})
            self.filters.set(KALMAN_KEY, {**kalman.to_dict(), "as_of": when.isoformat()})
        return RegimeInputs(
            as_of=when,
            vix=vix,
            nifty_close=closes[-1],
            nifty_vs_sma50=vs_sma,
            ewma_vol_ann=ewma.vol_ann,
            kalman_trend=kalman.trend,
            kalman_trend_z=kalman.trend_z(cfg.trend_z_window),
            kalman_trend_ann_pct=kalman.trend_ann_pct,
            vix_source=vix_source,
            notes=notes,
        )

    def run(self, as_of: datetime | date | None = None, *, hydrate: bool = True) -> RegimeJobResult:
        try:
            inputs = self.build_regime_inputs(as_of, persist=True, hydrate=hydrate)
        except ValueError as exc:
            logger.warning("regime inputs failed: {}", exc)
            return RegimeJobResult(error=str(exc))
        cfg = self.settings.regime
        prior = self.regimes.previous(inputs.as_of)
        state = self.filters.get(DETECTOR_KEY) or {}
        current = state.get("label") or (prior.label if prior else None)
        since = _parse_date(state.get("since")) or (prior.as_of.date() if prior else None)
        pending = state.get("pending")
        pending_days = int(state.get("pending_days") or 0)
        decision = decide(
            inputs,
            cfg,
            current=current,
            since=since,
            pending=pending,
            pending_days=pending_days,
        )
        since_out = inputs.as_of.date() if decision.label != current else (since or inputs.as_of.date())
        self.filters.set(
            DETECTOR_KEY,
            {
                "label": decision.label,
                "since": since_out.isoformat(),
                "pending": decision.pending,
                "pending_days": decision.pending_days,
            },
        )
        self.regimes.upsert(
            RegimeSnapshot(
                as_of=inputs.as_of,
                label=decision.label,
                soft_calm=Decimal(str(decision.soft["Calm"])),
                soft_elevated=Decimal(str(decision.soft["Elevated"])),
                soft_stress=Decimal(str(decision.soft["Stress"])),
                vix=dec(inputs.vix),
                ewma_vol_ann=dec(inputs.ewma_vol_ann),
                kalman_trend_z=dec(inputs.kalman_trend_z),
                nifty_vs_sma50=dec(inputs.nifty_vs_sma50),
                reason=decision.reason,
                vix_source=inputs.vix_source,
            )
        )
        logger.info("regime {} as_of={} {}", decision.label, inputs.as_of.date(), decision.reason)
        return RegimeJobResult(
            label=decision.label,
            as_of=inputs.as_of,
            reason=decision.reason,
            vix_source=inputs.vix_source,
        )

    def latest_view(self) -> dict[str, str]:
        row = self.regimes.latest()
        if not row:
            return {
                "label": "Unscored",
                "tone": "idle",
                "note": "Run python -m meridian regime after the tape is marked.",
            }
        tone = row.label.lower()
        return {"label": row.label, "tone": tone, "note": row.reason or ""}

    def _nifty_yahoo(self) -> str:
        primary = self.settings.market.nifty_ticker
        if self.bars.count(primary) >= 40:
            return primary
        fallback = self.settings.market.nifty_fallback
        if fallback and self.bars.count(fallback) >= 40:
            return fallback
        return primary

    def _closes(
        self, yahoo: str, as_of: datetime, history_days: int
    ) -> tuple[list[float], list[datetime]]:
        rows = self.bars.list(yahoo, limit=history_days + 20)
        closes: list[float] = []
        dates: list[datetime] = []
        for bar in rows:
            if bar.close is None:
                continue
            if bar.bar_date.date() > as_of.date():
                continue
            closes.append(float(bar.close))
            dates.append(bar.bar_date)
        return closes, dates

    def _resolve_vix(self, as_of: datetime, vol_ann: float) -> tuple[float | None, str, list[str]]:
        notes: list[str] = []
        ticker = self.settings.market.vix_ticker
        closes, _ = self._closes(ticker, as_of, 40)
        if closes:
            return closes[-1], "india_vix", notes
        quote = self.quotes.get("INDIAVIX", "INDEX")
        if quote and quote.last_price is not None:
            if quote.as_of is None or quote.as_of.date() <= as_of.date():
                return float(quote.last_price), "quote", notes
        implied = vol_ann * 100.0
        notes.append(f"VIX missing; scaled EWMA vol → {implied:.1f}")
        logger.warning("India VIX bars missing; using scaled EWMA vol {:.2f}", implied)
        return implied, "ewma_scaled", notes

    def _hydrate(self, history_days: int) -> None:
        from meridian.data_providers.service import PriceService, _period_for_days

        prices = PriceService(self.session)
        period = _period_for_days(max(history_days, 280))
        for ticker in (
            self.settings.market.nifty_ticker,
            self.settings.market.vix_ticker,
            self.settings.market.nifty_fallback,
        ):
            if not ticker:
                continue
            need = self.bars.count(ticker) < min(history_days, 120)
            last = self.bars.last_date(ticker)
            stale = last is None or (datetime.now() - last).days > 4
            if not (need or stale):
                continue
            provider = prices._provider()
            if provider is None:
                continue
            fetched = provider.history([ticker], period=period)
            bars = fetched.get(ticker, [])
            if bars:
                prices._store_bars(ticker, bars)


def _as_dt(value: datetime | date) -> datetime:
    if isinstance(value, datetime):
        return datetime.combine(value.date(), datetime.min.time())
    return datetime.combine(value, datetime.min.time())


def _parse_date(raw: object) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None
