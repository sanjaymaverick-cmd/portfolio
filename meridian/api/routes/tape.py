from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from meridian.api.deps import db_session
from meridian.data_providers.service import PriceService

router = APIRouter(prefix="/tape", tags=["tape"])


@router.get("")
def tape_status(session: Session = Depends(db_session)) -> dict:
    snap = PriceService(session).snapshot()
    return {
        "last_ok": snap.last_ok.isoformat() if snap.last_ok else None,
        "last_run": snap.last_run.isoformat() if snap.last_run else None,
        "stale": snap.stale,
        "error": snap.last_error,
        "nifty": None if snap.nifty_last is None else float(snap.nifty_last),
        "nifty_chg": None if snap.nifty_chg is None else float(snap.nifty_chg),
        "vix": None if snap.vix_last is None else float(snap.vix_last),
        "vix_chg": None if snap.vix_chg is None else float(snap.vix_chg),
    }


@router.post("/refresh")
def tape_refresh(
    force: bool = Query(default=False),
    session: Session = Depends(db_session),
) -> dict:
    result = PriceService(session).refresh(force=force, history=True)
    return {
        "marked": result.marked,
        "skipped": result.skipped,
        "failed": result.failed,
        "error": result.error,
    }
