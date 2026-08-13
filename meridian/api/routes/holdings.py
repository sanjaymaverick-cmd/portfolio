from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from meridian.api.deps import db_session
from meridian.api.schemas import HoldingIn, HoldingPatch
from meridian.domain.models import MappedRow
from meridian.ingestion.service import ImportService
from meridian.storage.repositories import HoldingRepo

router = APIRouter(prefix="/holdings", tags=["holdings"])


@router.get("")
def list_holdings(
    account: int | None = None,
    q: str | None = None,
    session: Session = Depends(db_session),
) -> list[dict]:
    repo = HoldingRepo(session)
    return [repo.to_view(row).model_dump(mode="json") for row in repo.list(account_id=account, query=q)]


@router.post("")
def create_holding(payload: HoldingIn, session: Session = Depends(db_session)) -> dict:
    service = ImportService(session)
    service.add_manual(
        payload.account_name,
        MappedRow(
            symbol=payload.symbol,
            exchange=payload.exchange,
            company_name=payload.company_name,
            quantity=payload.quantity,
            avg_cost=payload.avg_cost,
            last_price=payload.last_price,
            sector=payload.sector,
        ),
    )
    return {"status": "ok"}


@router.patch("/{holding_id}")
def patch_holding(
    holding_id: int, payload: HoldingPatch, session: Session = Depends(db_session)
) -> dict:
    repo = HoldingRepo(session)
    holding = repo.get(holding_id)
    if not holding:
        raise HTTPException(404, "Holding not found")
    repo.update_manual(holding, **payload.model_dump(exclude_unset=True))
    return repo.to_view(holding).model_dump(mode="json")


@router.delete("/{holding_id}")
def delete_holding(holding_id: int, session: Session = Depends(db_session)) -> dict:
    repo = HoldingRepo(session)
    holding = repo.get(holding_id)
    if not holding:
        raise HTTPException(404, "Holding not found")
    repo.delete(holding)
    return {"status": "deleted"}
