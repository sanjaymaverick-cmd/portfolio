from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from meridian.api.deps import db_session
from meridian.recommendations.alert_service import AlertService
from meridian.storage.alerts import AlertRepo

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def list_alerts(session: Session = Depends(db_session)) -> dict:
    rows = AlertRepo(session).open_alerts()
    return {
        "open": [_dump(row) for row in rows],
        "count": len(rows),
    }


@router.post("/evaluate")
def evaluate(session: Session = Depends(db_session)) -> dict:
    result = AlertService(session).evaluate()
    return {
        "as_of": result.as_of.date().isoformat() if result.as_of else None,
        "opened": result.opened,
        "closed": result.closed,
        "names": result.names,
    }


def _dump(row) -> dict:  # noqa: ANN001
    return {
        "id": row.id,
        "symbol": row.symbol,
        "kind": row.kind,
        "severity": row.severity,
        "title": row.title,
        "detail": row.detail,
        "action": row.action,
        "status": row.status,
    }
