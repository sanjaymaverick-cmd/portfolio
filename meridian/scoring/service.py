from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from meridian.config import Settings, get_settings
from meridian.data_providers.screener import FundamentalSnap, ScreenerProvider
from meridian.data_providers.yahoo_fundamentals import YahooFundamentals
from meridian.scoring.composite import CompositeService
from meridian.scoring.ownership import score_ownership
from meridian.scoring.quality import score_quality
from meridian.scoring.sentiment import score_sentiment
from meridian.scoring.valuation import score_valuation
from meridian.storage.fundamentals import FactorRepo, FundamentalRepo
from meridian.storage.market import SettingRepo
from meridian.storage.repositories import HoldingRepo


@dataclass
class FundRefresh:
    marked: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    error: str | None = None


class FundamentalService:
    def __init__(
        self,
        session: Session,
        provider: ScreenerProvider | None = None,
        fallback: YahooFundamentals | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.provider = provider
        self.fallback = fallback if fallback is not None else YahooFundamentals()
        self.fundamentals = FundamentalRepo(session)
        self.factors = FactorRepo(session)
        self.holdings = HoldingRepo(session)
        self.settings_repo = SettingRepo(session)

    def refresh(self, *, force: bool = False, symbol: str | None = None) -> FundRefresh:
        result = FundRefresh()
        self.settings_repo.set("fundamentals.last_run", datetime.now().isoformat(timespec="seconds"))
        if not self.settings.providers.screener_enabled and self.provider is None:
            result.error = "Screener disabled in config"
            return result
        ttl = timedelta(hours=self.settings.providers.screener_ttl_hours)
        now = datetime.now()
        rows = self.holdings.list()
        if symbol:
            rows = [row for row in rows if row.symbol.upper() == symbol.upper()]
        seen: set[str] = set()
        provider = self.provider or ScreenerProvider(sleep_ms=self.settings.providers.screener_sleep_ms)
        for holding in rows:
            key = holding.symbol.upper()
            if key in seen:
                continue
            seen.add(key)
            existing = self.fundamentals.get(key)
            fresh = (
                existing is not None
                and existing.fetched_at is not None
                and (now - existing.fetched_at) <= ttl
            )
            if fresh and not force:
                result.skipped += 1
                continue
            snap = provider.fetch(key)
            if snap is None and self.fallback is not None:
                snap = self.fallback.fetch(key, holding.yahoo)
            if snap is None:
                result.failed.append(key)
                continue
            self.persist(snap)
            result.marked += 1
        if result.marked or result.skipped:
            CompositeService(self.session, self.settings).recompute(symbol)
        if result.failed:
            self.settings_repo.set(
                "fundamentals.last_error", "No fundamentals: " + ", ".join(result.failed[:8])
            )
        else:
            self.settings_repo.set("fundamentals.last_error", "")
        if result.marked or result.skipped:
            self.settings_repo.set("fundamentals.last_ok", datetime.now().isoformat(timespec="seconds"))
        logger.info(
            "fundamentals marked={} skipped={} failed={}",
            result.marked,
            result.skipped,
            len(result.failed),
        )
        return result

    def persist(self, snap: FundamentalSnap) -> None:
        self.fundamentals.upsert(snap)
        quality, q_parts = score_quality(snap)
        valuation, v_parts = score_valuation(snap)
        ownership, o_parts = score_ownership(snap)
        sentiment, s_parts = score_sentiment(snap)
        self.factors.patch(
            snap.symbol,
            source=snap.source,
            quality=quality,
            valuation=valuation,
            ownership=ownership,
            sentiment=sentiment,
            quality_detail=_dump(q_parts),
            valuation_detail=_dump(v_parts),
            ownership_detail=_dump(o_parts),
            sentiment_detail=_dump(s_parts),
        )
        if snap.sector:
            for holding in self.holdings.list():
                if holding.symbol.upper() == snap.symbol and holding.sector == "Unclassified":
                    holding.sector = snap.sector

    def snapshot_status(self) -> dict[str, str | None]:
        return {
            "last_ok": self.settings_repo.get("fundamentals.last_ok"),
            "last_run": self.settings_repo.get("fundamentals.last_run"),
            "last_error": self.settings_repo.get("fundamentals.last_error"),
        }


def _dump(parts: dict[str, Decimal | None]) -> str:
    return json.dumps({key: None if value is None else float(value) for key, value in parts.items()})
