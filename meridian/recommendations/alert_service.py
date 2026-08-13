from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from meridian.config import Settings, get_settings
from meridian.recommendations.alerts import (
    action_hit,
    pledge_hit,
    regime_hit,
    results_hit,
    volume_hit,
    weight_hit,
)
from meridian.storage.alerts import AlertRepo
from meridian.storage.attributions import AttributionRepo
from meridian.storage.fundamentals import FundamentalRepo
from meridian.storage.regime import RegimeRepo
from meridian.storage.repositories import HoldingRepo
from meridian.storage.risk import RiskRepo
from meridian.storage.schema import AlertEvent, Attribution, DailyNews, Holding


@dataclass
class AlertResult:
    as_of: datetime | None = None
    opened: int = 0
    closed: int = 0
    names: list[str] = field(default_factory=list)


class AlertService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = AlertRepo(session)
        self.holdings = HoldingRepo(session)
        self.funds = FundamentalRepo(session)
        self.risk = RiskRepo(session)
        self.attr = AttributionRepo(session)
        self.regime = RegimeRepo(session)

    def evaluate(self, as_of: datetime | None = None) -> AlertResult:
        when = datetime.combine((as_of or datetime.now()).date(), datetime.min.time())
        cfg = self.settings.alerts
        rows = self.holdings.list()
        book = self.holdings.summary(rows)
        by_symbol = _aggregate(rows)
        hits = []
        for symbol, line in by_symbol.items():
            weight = None
            if book.market_value and line.value:
                weight = float(line.value / book.market_value * Decimal("100"))
            if weight is not None:
                hits.append(
                    weight_hit(symbol, weight, threshold=cfg.weight_pct, high=cfg.weight_high_pct)
                )
            fund = self.funds.get(symbol)
            if fund:
                hits.append(
                    pledge_hit(
                        symbol,
                        _f(fund.promoter_pledge),
                        _f(fund.promoter_pledge_prev),
                        step=cfg.pledge_step_pp,
                        abs_limit=cfg.pledge_abs,
                    )
                )
            risk = self.risk.get(symbol)
            if risk:
                hits.append(volume_hit(symbol, _f(risk.volume_ratio), threshold=cfg.volume_ratio))
            current, previous = self._actions(symbol)
            hits.append(action_hit(symbol, current, previous))
            titles, published = self._result_headlines(symbol, when, cfg.results_lookback_days)
            hits.append(results_hit(symbol, titles, when, published, lookback_days=cfg.results_lookback_days))
        latest = self.regime.latest()
        prior = self.regime.previous(latest.as_of) if latest else None
        hits.append(regime_hit(latest.label if latest else None, prior.label if prior else None))
        keep: set[tuple[str, str]] = set()
        result = AlertResult(as_of=when)
        for hit in [item for item in hits if item]:
            attr = None if hit.symbol == "MARKET" else self.attr.latest(hit.symbol)
            self.repo.upsert(
                AlertEvent(
                    as_of=when,
                    kind=hit.kind,
                    symbol=hit.symbol,
                    severity=hit.severity,
                    title=hit.title,
                    detail=hit.detail,
                    shap_note=_shap_note(attr),
                    action=attr.action if attr else None,
                    status="open",
                    payload=json.dumps({"metric": hit.metric}),
                )
            )
            keep.add((hit.kind, hit.symbol))
            result.names.append(hit.symbol)
        result.opened = len(keep)
        result.closed = self.repo.close_missing(when, keep)
        return result

    def _actions(self, symbol: str) -> tuple[str | None, str | None]:
        latest = self.attr.latest(symbol)
        previous = self.attr.previous(symbol)
        return (latest.action if latest else None, previous.action if previous else None)

    def _result_headlines(
        self, symbol: str, as_of: datetime, lookback: int
    ) -> tuple[list[str], datetime | None]:
        from sqlalchemy import select

        start = as_of - timedelta(days=lookback)
        news = list(
            self.session.scalars(
                select(DailyNews).where(
                    DailyNews.symbol == symbol.upper(),
                    DailyNews.kept.is_(True),
                    DailyNews.aspect == "Results",
                    DailyNews.as_of >= start,
                )
            )
        )
        titles = [row.title for row in news]
        published = None
        for row in news:
            stamp = row.published or row.as_of
            if stamp and (published is None or stamp > published):
                published = stamp
        return titles, published


@dataclass
class _Name:
    symbol: str
    value: Decimal


def _aggregate(rows: list[Holding]) -> dict[str, _Name]:
    out: dict[str, _Name] = {}
    for holding in rows:
        key = holding.symbol.upper()
        value = holding.quantity * holding.last_price if holding.last_price is not None else Decimal("0")
        if key in out:
            out[key].value += value
        else:
            out[key] = _Name(symbol=key, value=value)
    return out


def _f(value) -> float | None:  # noqa: ANN001
    if value is None:
        return None
    return float(value)


def _shap_note(attr: Attribution | None) -> str | None:
    if attr is None or not attr.reasoning:
        return None
    text = attr.reasoning.split(" This is a monitor")[0].strip()
    return text[:400] or None
