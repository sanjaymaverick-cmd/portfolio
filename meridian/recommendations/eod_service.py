from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from meridian.config import Settings, get_settings
from meridian.data_providers.news import fetch_symbol_news
from meridian.recommendations.eod_llm import llm_attribution
from meridian.recommendations.eod_rules import rule_attribution, validate_payload
from meridian.scoring.news_filter import Headline, filter_headlines
from meridian.storage.eod import EodRepo
from meridian.storage.market import QuoteRepo
from meridian.storage.repositories import HoldingRepo
from meridian.storage.schema import DailyImpact, DailyNews, DailyPerformance, Holding


@dataclass
class EodResult:
    as_of: datetime | None = None
    selected: int = 0
    news: int = 0
    attributed: int = 0
    skipped: str | None = None
    error: str | None = None
    names: list[str] = field(default_factory=list)


class EodService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.holdings = HoldingRepo(session)
        self.quotes = QuoteRepo(session)
        self.repo = EodRepo(session)

    def run(
        self,
        as_of: datetime | None = None,
        *,
        force: bool = False,
        fetch: bool = True,
        headlines_by_symbol: dict[str, list[Headline]] | None = None,
    ) -> EodResult:
        cfg = self.settings.eod
        when = datetime.combine((as_of or datetime.now()).date(), datetime.min.time())
        if cfg.skip_weekends and when.weekday() >= 5 and not force:
            return EodResult(as_of=when, skipped="weekend")
        rows = self.holdings.list()
        if not rows:
            return EodResult(as_of=when, error="empty book")
        self.repo.clear_day(when)
        lines = _aggregate(rows)
        selected = _pick_movers(lines, move_pct=cfg.move_pct, top_n=cfg.top_n, max_names=cfg.max_names)
        nifty_chg = self._nifty_chg()
        result = EodResult(as_of=when, selected=len(selected), names=[item.symbol for item in selected])
        for line in lines:
            self.repo.add_perf(
                DailyPerformance(
                    as_of=when,
                    symbol=line.symbol,
                    company_name=line.company,
                    day_pnl=line.day_pnl,
                    day_pnl_pct=line.day_pct,
                    contribution=line.contribution,
                    last_price=line.last,
                    prev_close=line.prev,
                    selected=line.symbol in {item.symbol for item in selected},
                    why=line.why,
                )
            )
        for line in selected:
            if headlines_by_symbol is not None:
                raw = list(headlines_by_symbol.get(line.symbol, []))
            elif fetch:
                raw = fetch_symbol_news(line.symbol, line.company, sleep_ms=cfg.news_sleep_ms)
            else:
                raw = []
            kept = filter_headlines(raw, symbol=line.symbol, company=line.company, keep=cfg.keep_headlines)
            result.news += len(kept)
            for item in kept:
                self.repo.add_news(_news_row(when, line.symbol, item))
            payload = self._attribute(line.symbol, float(line.day_pct or 0), kept, nifty_chg)
            self.repo.upsert_impact(
                DailyImpact(
                    as_of=when,
                    symbol=line.symbol,
                    engine=payload.get("_engine", "rules"),
                    takeaway=payload.get("takeaway"),
                    market_context=payload.get("market_context"),
                    confidence=Decimal(str(payload.get("confidence", 0.4))),
                    positives=json.dumps(payload.get("positive") or []),
                    negatives=json.dumps(payload.get("negative") or []),
                    payload=json.dumps(payload),
                )
            )
            result.attributed += 1
        logger.info(
            "eod as_of={} selected={} news={} attributed={}",
            when.date(),
            result.selected,
            result.news,
            result.attributed,
        )
        return result

    def _attribute(
        self, symbol: str, day_pct: float, headlines: list[Headline], nifty_chg: float | None
    ) -> dict:
        rules = rule_attribution(symbol=symbol, day_pct=day_pct, headlines=headlines, nifty_chg=nifty_chg)
        cfg = self.settings.eod
        url = cfg.llm_url or os.environ.get("MERIDIAN_LLM_URL", "")
        model = cfg.llm_model or os.environ.get("MERIDIAN_LLM_MODEL", "")
        if cfg.llm_enabled and url:
            llm = llm_attribution(
                symbol=symbol,
                day_pct=day_pct,
                headlines=headlines,
                nifty_chg=nifty_chg,
                url=url,
                model=model,
                key=os.environ.get("MERIDIAN_LLM_KEY"),
            )
            if llm:
                cleaned = validate_payload(llm, headlines)
                if cleaned["positive"] or cleaned["negative"] or not headlines:
                    return cleaned | {"_engine": "llm"}
        rules["_engine"] = "rules"
        return rules

    def _nifty_chg(self) -> float | None:
        quote = self.quotes.get("NIFTY", "INDEX")
        if quote and quote.last_price is not None and quote.prev_close not in (None, 0):
            return float((quote.last_price - quote.prev_close) / quote.prev_close * 100)
        return None


@dataclass
class _Line:
    symbol: str
    company: str | None
    last: Decimal | None
    prev: Decimal | None
    day_pnl: Decimal | None
    day_pct: Decimal | None
    contribution: Decimal | None
    why: str | None = None


def _aggregate(rows: list[Holding]) -> list[_Line]:
    buckets: dict[str, _Line] = {}
    for holding in rows:
        key = holding.symbol.upper()
        line = buckets.get(key)
        day = None
        if holding.last_price is not None and holding.prev_close is not None:
            day = holding.quantity * (holding.last_price - holding.prev_close)
        pct = None
        if holding.last_price is not None and holding.prev_close not in (None, 0):
            pct = (holding.last_price - holding.prev_close) / holding.prev_close * Decimal("100")
        if line is None:
            buckets[key] = _Line(
                symbol=key,
                company=holding.company_name,
                last=holding.last_price,
                prev=holding.prev_close,
                day_pnl=day,
                day_pct=pct,
                contribution=day,
            )
        else:
            if day is not None:
                line.contribution = (line.contribution or Decimal("0")) + day
                line.day_pnl = (line.day_pnl or Decimal("0")) + day
    return list(buckets.values())


def _pick_movers(lines: list[_Line], *, move_pct: float, top_n: int, max_names: int) -> list[_Line]:
    by_pct = [line for line in lines if line.day_pct is not None and abs(float(line.day_pct)) >= move_pct]
    for line in by_pct:
        line.why = "threshold"
    rest = [line for line in lines if line not in by_pct and line.contribution is not None]
    rest.sort(key=lambda item: abs(float(item.contribution or 0)), reverse=True)
    for line in rest[:top_n]:
        line.why = "contribution"
        by_pct.append(line)
    by_pct.sort(key=lambda item: abs(float(item.day_pct or 0)), reverse=True)
    return by_pct[:max_names]


def _news_row(as_of: datetime, symbol: str, item: Headline) -> DailyNews:
    return DailyNews(
        as_of=as_of,
        symbol=symbol,
        title=item.title[:400],
        url=(item.url or "")[:500] or None,
        source=item.source[:80],
        published=item.published,
        sentiment=Decimal(str(round(item.sentiment, 4))),
        aspect=item.aspect,
        rank=Decimal(str(round(item.rank, 4))),
        is_filing=item.is_filing,
        kept=item.kept,
    )
