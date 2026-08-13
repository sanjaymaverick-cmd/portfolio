from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.alerts.worker import current_regime
from meridian_v2.config import get_settings
from meridian_v2.scoring.service import ScoringService
from meridian_v2.storage.schema import BookLegRow, DeskEvent, FxMark, NewsStub, PriceCache, WatchItem


def capture_desk_state(session: Session, symbol: str) -> dict:
    settings = get_settings()
    regime = current_regime(session, settings)
    scores = ScoringService(session).latest()
    score = scores.get(symbol.upper())
    price = session.scalar(
        select(PriceCache).where(PriceCache.symbol == symbol.upper(), PriceCache.contract_label == "CONTINUOUS")
    )
    news = list(
        session.scalars(select(NewsStub).where(NewsStub.symbol == symbol.upper()).order_by(NewsStub.as_of.desc()).limit(3))
    )
    fx = list(session.scalars(select(FxMark)))
    return {
        "as_of": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
        "symbol": symbol.upper(),
        "regime": regime.value,
        "score": score.composite if score else None,
        "stance": score.stance if score else "",
        "factors": {
            "technical": score.technical if score else None,
            "tape": score.tape if score else None,
            "news": score.news if score else None,
        }
        if score
        else {},
        "mark": price.last if price else None,
        "mark_quality": price.quality if price else "",
        "news": [{"headline": n.headline, "tone": n.tone} for n in news],
        "fx": {row.pair: {"last": row.last, "prev": row.prev_close} for row in fx},
    }


def has_prior_watch_or_ack(session: Session, symbol: str) -> bool:
    watched = session.scalar(select(WatchItem).where(WatchItem.symbol == symbol.upper()))
    acked = session.scalar(
        select(DeskEvent).where(
            DeskEvent.symbol == symbol.upper(),
            DeskEvent.status.in_(("accepted", "dismissed", "snoozed")),
        )
    )
    return watched is not None or acked is not None


def in_live_book(session: Session, symbol: str) -> bool:
    return session.scalar(select(BookLegRow).where(BookLegRow.symbol == symbol.upper())) is not None


def dumps(payload: dict) -> str:
    return json.dumps(payload, default=str)
