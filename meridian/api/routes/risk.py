from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from meridian.api.deps import db_session
from meridian.risk.service import BOOK, RiskService
from meridian.storage.risk import RiskRepo

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/portfolio")
def portfolio(session: Session = Depends(db_session)) -> dict:
    row = RiskRepo(session).get(BOOK)
    if not row:
        return {"status": "missing"}
    return _dump(row)


@router.get("/{symbol}")
def name_risk(symbol: str, session: Session = Depends(db_session)) -> dict:
    row = RiskRepo(session).get(symbol)
    if not row:
        return {"symbol": symbol.upper(), "status": "missing"}
    return _dump(row)


@router.post("/compute")
def compute(force: bool = Query(default=False), session: Session = Depends(db_session)) -> dict:
    result = RiskService(session).compute(force=force)
    return {
        "marked": result.marked,
        "skipped": result.skipped,
        "failed": result.failed,
        "error": result.error,
        "nifty": result.nifty,
    }


def _dump(row) -> dict:  # noqa: ANN001
    return {
        "symbol": row.symbol,
        "rho": None if row.rho is None else float(row.rho),
        "beta_ols": None if row.beta_ols is None else float(row.beta_ols),
        "beta_ewma": None if row.beta_ewma is None else float(row.beta_ewma),
        "beta_shrunk": None if row.beta_shrunk is None else float(row.beta_shrunk),
        "rsi": None if row.rsi is None else float(row.rsi),
        "window": row.window,
        "as_of": row.as_of.isoformat() if row.as_of else None,
    }
