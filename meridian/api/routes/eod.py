from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from meridian.api.deps import db_session
from meridian.recommendations.eod_service import EodService
from meridian.storage.eod import EodRepo, decode_list

router = APIRouter(prefix="/eod", tags=["eod"])


@router.get("/movers")
def movers(session: Session = Depends(db_session)) -> dict:
    repo = EodRepo(session)
    day = repo.latest_day()
    rows = repo.movers(day)
    return {
        "as_of": day.date().isoformat() if day else None,
        "movers": [_dump(perf, impact) for perf, impact in rows],
    }


@router.get("/{symbol}")
def name_eod(symbol: str, session: Session = Depends(db_session)) -> dict:
    repo = EodRepo(session)
    timeline = []
    for impact in repo.timeline(symbol):
        timeline.append(
            {
                "as_of": impact.as_of.date().isoformat(),
                "engine": impact.engine,
                "takeaway": impact.takeaway,
                "market_context": impact.market_context,
                "confidence": None if impact.confidence is None else float(impact.confidence),
                "positive": decode_list(impact.positives),
                "negative": decode_list(impact.negatives),
            }
        )
    if not timeline:
        return {"symbol": symbol.upper(), "status": "missing"}
    return {"symbol": symbol.upper(), "timeline": timeline}


@router.post("/run")
def run(
    force: bool = Query(default=False),
    fetch: bool = Query(default=True),
    session: Session = Depends(db_session),
) -> dict:
    result = EodService(session).run(force=force, fetch=fetch)
    return {
        "as_of": result.as_of.date().isoformat() if result.as_of else None,
        "selected": result.selected,
        "news": result.news,
        "attributed": result.attributed,
        "skipped": result.skipped,
        "error": result.error,
        "names": result.names,
    }


def _dump(perf, impact) -> dict:  # noqa: ANN001
    return {
        "symbol": perf.symbol,
        "company_name": perf.company_name,
        "day_pnl": None if perf.day_pnl is None else float(perf.day_pnl),
        "day_pnl_pct": None if perf.day_pnl_pct is None else float(perf.day_pnl_pct),
        "contribution": None if perf.contribution is None else float(perf.contribution),
        "why": perf.why,
        "engine": impact.engine if impact else None,
        "takeaway": impact.takeaway if impact else None,
        "confidence": None if not impact or impact.confidence is None else float(impact.confidence),
        "positive": decode_list(impact.positives) if impact else [],
        "negative": decode_list(impact.negatives) if impact else [],
        "market_context": impact.market_context if impact else None,
    }
