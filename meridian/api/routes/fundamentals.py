from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from meridian.api.deps import db_session
from meridian.scoring.service import FundamentalService
from meridian.storage.fundamentals import FactorRepo, FundamentalRepo

router = APIRouter(prefix="/fundamentals", tags=["fundamentals"])


@router.get("/{symbol}")
def get_fundamental(symbol: str, session: Session = Depends(db_session)) -> dict:
    row = FundamentalRepo(session).get(symbol)
    factor = FactorRepo(session).get(symbol)
    if not row:
        return {"symbol": symbol.upper(), "status": "missing"}
    return {
        "symbol": row.symbol,
        "source": row.source,
        "pe": None if row.pe is None else float(row.pe),
        "pb": None if row.pb is None else float(row.pb),
        "roe": None if row.roe is None else float(row.roe),
        "roce": None if row.roce is None else float(row.roce),
        "quality": None if not factor or factor.quality is None else float(factor.quality),
        "valuation": None if not factor or factor.valuation is None else float(factor.valuation),
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    }


@router.post("/refresh")
def refresh(
    force: bool = Query(default=False),
    symbol: str | None = Query(default=None),
    session: Session = Depends(db_session),
) -> dict:
    result = FundamentalService(session).refresh(force=force, symbol=symbol)
    return {
        "marked": result.marked,
        "skipped": result.skipped,
        "failed": result.failed,
        "error": result.error,
    }
