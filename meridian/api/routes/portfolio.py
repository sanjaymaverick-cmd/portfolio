from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from meridian.api.deps import db_session
from meridian.storage.repositories import AccountRepo, HoldingRepo

router = APIRouter(tags=["portfolio"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "product": "meridian"}


@router.get("/summary")
def summary(account: int | None = None, session: Session = Depends(db_session)) -> dict:
    holdings = HoldingRepo(session).list(account_id=account)
    book = HoldingRepo(session).summary(holdings)
    return book.model_dump(mode="json")


@router.get("/accounts")
def accounts(session: Session = Depends(db_session)) -> list[dict]:
    return [item.model_dump(mode="json") for item in AccountRepo(session).views()]
