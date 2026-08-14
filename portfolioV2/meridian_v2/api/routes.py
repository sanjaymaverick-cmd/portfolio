from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from meridian_v2.alerts.worker import current_regime
from meridian_v2.config import get_settings
from meridian_v2.risk.review_service import build_desk_review
from meridian_v2.signals.chart_service import chart_for_symbol
from meridian_v2.storage.db import get_session
from meridian_v2.watchlist.service import WatchlistError, WatchlistService

router = APIRouter()


class WatchIn(BaseModel):
    symbol: str
    asset_class: str = "equity"
    notes: str = ""


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "app": settings.app.name,
        "port": settings.app.port,
        "db": str(settings.db_path),
        "advisor_only": True,
    }


@router.get("/watch")
def watch_list() -> dict:
    session = get_session()
    try:
        svc = WatchlistService(session)
        items = svc.list_items()
        state = svc.cap_state()
        return {
            "cap": state["cap"],
            "active": state["active"],
            "remaining": state["remaining"],
            "warn": state["warn"],
            "at_cap": state["at_cap"],
            "items": [
                {
                    "id": i.id,
                    "symbol": i.symbol,
                    "asset_class": i.asset_class,
                    "status": i.status,
                    "notes": i.notes,
                }
                for i in items
            ],
        }
    finally:
        session.close()


@router.post("/watch")
def watch_add(body: WatchIn) -> dict:
    session = get_session()
    try:
        item = WatchlistService(session).add(body.symbol, body.asset_class, body.notes)
        session.commit()
        return {"id": item.id, "symbol": item.symbol, "status": item.status}
    except WatchlistError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@router.get("/review/{symbol}")
def review(symbol: str) -> dict:
    session = get_session()
    try:
        settings = get_settings()
        regime = current_regime(session, settings)
        return build_desk_review(session, symbol.upper(), regime=regime)
    finally:
        session.close()


@router.get("/templates")
def templates() -> dict:
    from meridian_v2.domain.templates import catalog_payload

    return catalog_payload()


@router.get("/chart/{symbol}")
def chart(symbol: str) -> dict:
    session = get_session()
    try:
        return chart_for_symbol(session, symbol.upper())
    finally:
        session.close()
