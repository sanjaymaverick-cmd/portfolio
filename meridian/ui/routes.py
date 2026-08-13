from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from meridian.api.deps import db_session, int_or_none
from meridian.config import get_settings
from meridian.domain.models import MappedRow
from meridian.domain.money import to_decimal
from meridian.data_providers.service import PriceService
from meridian.ingestion.columns import FIELD_ALIASES
from meridian.ingestion.service import ImportService
from meridian.scoring.service import FundamentalService
from meridian.storage.fundamentals import FactorRepo, FundamentalRepo
from meridian.storage.repositories import AccountRepo, HoldingRepo, ImportRepo
from meridian.storage.seed import seed_demo
from meridian.risk.service import BOOK, RiskService
from meridian.scoring.regime_service import RegimeInputService
from meridian.storage.regime import RegimeRepo
from meridian.storage.risk import RiskRepo
from meridian.storage.attributions import AttributionRepo
from meridian.storage.eod import EodRepo, decode_list
from meridian.recommendations.eod_service import EodService
from meridian.ui.charts import price_chart_html, risk_chart_html, shap_bar_html, sparkline
from meridian.ui.formatters import FILTERS

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
for name, fn in FILTERS.items():
    templates.env.filters[name] = fn

router = APIRouter()
_PREVIEWS: dict[str, Any] = {}


def _ctx(request: Request, session: Session, **extra: Any) -> dict[str, Any]:
    settings = get_settings()
    accounts = AccountRepo(session).views()
    account_id = int_or_none(request.query_params.get("account")) or int_or_none(
        request.cookies.get("account")
    )
    tape = PriceService(session).snapshot()
    return {
        "request": request,
        "app_name": settings.app.name,
        "subtitle": settings.app.subtitle,
        "theme": settings.app.theme,
        "now": datetime.now(),
        "accounts": accounts,
        "account_id": account_id,
        "tape": tape,
        "book_risk": RiskRepo(session).get(BOOK),
        "market": settings.market,
        "regime": RegimeInputService(session).latest_view(),
        "regime_snap": RegimeRepo(session).latest(),
        **extra,
    }


def _with_sparks(session, views):  # noqa: ANN001
    service = PriceService(session)
    factors = FactorRepo(session).map_for([view.symbol for view in views])
    for view in views:
        closes = service.closes(view.yahoo, limit=30)
        view.spark = sparkline(closes)
        row = factors.get(view.symbol)
        if row:
            view.quality = row.quality
            view.valuation = row.valuation
            view.technical = row.technical
            view.ownership = row.ownership
            view.sentiment = row.sentiment
            view.score = row.composite
            view.action = row.action or "—"
            view.recommendation = row.action or "—"
            view.confidence = row.confidence
    risks = RiskRepo(session).map_for([view.symbol for view in views])
    for view in views:
        risk = risks.get(view.symbol)
        if risk:
            view.rho = risk.rho
            view.beta = risk.beta_shrunk or risk.beta_ewma
            view.beta_ols = risk.beta_ols
            view.beta_ewma = risk.beta_ewma
            view.rsi = risk.rsi
    return views


@router.get("/", response_class=HTMLResponse)
def command(request: Request, session: Session = Depends(db_session)) -> HTMLResponse:
    account_id = int_or_none(request.query_params.get("account"))
    repo = HoldingRepo(session)
    rows = repo.list(account_id=account_id)
    views = _with_sparks(session, [repo.to_view(row) for row in rows])
    book = repo.summary(rows)
    movers = sorted(
        [v for v in views if v.day_pnl_pct is not None],
        key=lambda item: abs(item.day_pnl_pct or 0),
        reverse=True,
    )[:5]
    if not movers:
        movers = sorted(
            [v for v in views if v.pnl_pct is not None],
            key=lambda item: abs(item.pnl_pct or 0),
            reverse=True,
        )[:5]
    eod_cards, eod_as_of = _eod_cards(session, views)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        _ctx(
            request,
            session,
            active="command",
            holdings=views,
            book=book,
            movers=movers,
            eod_cards=eod_cards,
            eod_as_of=eod_as_of,
            jobs=ImportRepo(session).recent(5),
        ),
    )


@router.get("/holdings", response_class=HTMLResponse)
def holdings_page(request: Request, session: Session = Depends(db_session)) -> HTMLResponse:
    account_id = int_or_none(request.query_params.get("account"))
    query = request.query_params.get("q")
    sector = request.query_params.get("sector")
    repo = HoldingRepo(session)
    rows = repo.list(account_id=account_id, query=query, sector=sector)
    views = _with_sparks(session, [repo.to_view(row) for row in rows])
    book = repo.summary(rows)
    sectors = sorted({v.sector for v in views})
    return templates.TemplateResponse(
        request,
        "holdings.html",
        _ctx(
            request,
            session,
            active="holdings",
            holdings=views,
            book=book,
            sectors=sectors,
            query=query or "",
            sector=sector or "all",
        ),
    )


@router.get("/holdings/{holding_id}", response_class=HTMLResponse)
def holding_detail(
    holding_id: int, request: Request, session: Session = Depends(db_session)
) -> HTMLResponse:
    repo = HoldingRepo(session)
    holding = repo.get(holding_id)
    if not holding:
        return RedirectResponse("/holdings", status_code=303)
    view = repo.to_view(holding)
    book = repo.summary()
    weight = None
    if book.market_value and view.market_value:
        weight = (view.market_value / book.market_value) * Decimal("100")
    service = PriceService(session)
    bars = service.bars.list(view.yahoo, limit=get_settings().providers.history_days)
    chart = price_chart_html(view.symbol, bars)
    factor = FactorRepo(session).get(view.symbol)
    if factor:
        view.quality = factor.quality
        view.valuation = factor.valuation
        view.technical = factor.technical
        view.ownership = factor.ownership
        view.sentiment = factor.sentiment
        view.score = factor.composite
        view.action = factor.action or "—"
        view.recommendation = factor.action or "—"
        view.confidence = factor.confidence
    fundamental = FundamentalRepo(session).get(view.symbol)
    risk = RiskRepo(session).get(view.symbol)
    if risk:
        view.rho = risk.rho
        view.beta = risk.beta_shrunk or risk.beta_ewma
    risk_chart = risk_chart_html(view.symbol, RiskRepo(session).points(view.symbol))
    attribution = AttributionRepo(session).latest(view.symbol)
    shap_phis = _parts(attribution.phis if attribution else None)
    return templates.TemplateResponse(
        request,
        "detail.html",
        _ctx(
            request,
            session,
            active="holdings",
            holding=view,
            weight=weight,
            book=book,
            chart_html=chart,
            factor=factor,
            fundamental=fundamental,
            quality_parts=_parts(factor.quality_detail if factor else None),
            valuation_parts=_parts(factor.valuation_detail if factor else None),
            technical_parts=_parts(factor.technical_detail if factor else None),
            ownership_parts=_parts(factor.ownership_detail if factor else None),
            sentiment_parts=_parts(factor.sentiment_detail if factor else None),
            rec_note=(attribution.reasoning if attribution else _rec_note(factor)),
            portfolio_note=(attribution.portfolio_note if attribution else ""),
            shap_chart=shap_bar_html(view.symbol, {k: float(v) for k, v in shap_phis.items() if v is not None}),
            shap_engine=(attribution.engine if attribution else None),
            risk=risk,
            risk_chart=risk_chart,
            bar_count=len(bars),
            eod_timeline=_eod_timeline(session, view.symbol),
        ),
    )


@router.post("/tape/refresh")
def refresh_tape(
    request: Request,
    session: Session = Depends(db_session),
    next_url: str = Form("/"),
    force: str = Form(""),
) -> RedirectResponse:
    PriceService(session).refresh(force=bool(force), history=True)
    target = next_url if next_url.startswith("/") else "/"
    return RedirectResponse(target, status_code=303)


@router.post("/fundamentals/refresh")
def refresh_fundamentals(
    request: Request,
    session: Session = Depends(db_session),
    next_url: str = Form("/"),
    force: str = Form(""),
    symbol: str = Form(""),
) -> RedirectResponse:
    FundamentalService(session).refresh(force=bool(force), symbol=symbol or None)
    target = next_url if next_url.startswith("/") else "/"
    return RedirectResponse(target, status_code=303)


def _parts(raw: str | None) -> dict[str, float | None]:
    if not raw:
        return {}
    import json

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _rec_note(factor) -> str:  # noqa: ANN001
    if factor is None or not factor.action:
        return ""
    from meridian.scoring.composite import brief_reason

    return brief_reason(factor, factor.action, None)


def _eod_cards(session: Session, views) -> tuple[list[dict[str, Any]], datetime | None]:  # noqa: ANN001
    repo = EodRepo(session)
    day = repo.latest_day()
    rows = repo.movers(day)
    ids = {view.symbol: view.id for view in views}
    cards: list[dict[str, Any]] = []
    for perf, impact in rows:
        cards.append(
            {
                "symbol": perf.symbol,
                "company": perf.company_name,
                "holding_id": ids.get(perf.symbol),
                "day_pct": perf.day_pnl_pct,
                "day_pnl": perf.day_pnl,
                "contribution": perf.contribution,
                "why": perf.why,
                "engine": impact.engine if impact else None,
                "takeaway": impact.takeaway if impact else None,
                "confidence": impact.confidence if impact else None,
                "positives": decode_list(impact.positives) if impact else [],
                "negatives": decode_list(impact.negatives) if impact else [],
                "market": impact.market_context if impact else None,
            }
        )
    return cards, day


def _eod_timeline(session: Session, symbol: str) -> list[dict[str, Any]]:
    repo = EodRepo(session)
    out: list[dict[str, Any]] = []
    for impact in repo.timeline(symbol):
        out.append(
            {
                "as_of": impact.as_of,
                "engine": impact.engine,
                "takeaway": impact.takeaway,
                "market": impact.market_context,
                "confidence": impact.confidence,
                "positives": decode_list(impact.positives),
                "negatives": decode_list(impact.negatives),
                "news": repo.news_for(impact.as_of, symbol),
            }
        )
    return out


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request, session: Session = Depends(db_session)) -> HTMLResponse:
    token = request.query_params.get("preview")
    bundle = _PREVIEWS.get(token) if token else None
    preview = bundle["preview"] if bundle else None
    return templates.TemplateResponse(
        request,
        "import.html",
        _ctx(
            request,
            session,
            active="import",
            preview=preview,
            preview_token=token,
            field_aliases=FIELD_ALIASES,
            jobs=ImportRepo(session).recent(8),
        ),
    )


@router.post("/import/preview")
async def import_preview(
    request: Request,
    session: Session = Depends(db_session),
    statement: UploadFile = File(...),
) -> RedirectResponse:
    settings = get_settings()
    dest = settings.import_dir / f"{uuid4().hex}_{statement.filename}"
    dest.write_bytes(await statement.read())
    preview = ImportService(session).preview(dest)
    token = uuid4().hex
    _PREVIEWS[token] = {"preview": preview, "path": str(dest)}
    return RedirectResponse(f"/import?preview={token}", status_code=303)


@router.post("/import/commit")
async def import_commit(
    request: Request,
    session: Session = Depends(db_session),
    token: str = Form(...),
    account_name: str = Form(...),
    broker: str = Form("generic"),
) -> RedirectResponse:
    payload = _PREVIEWS.pop(token, None)
    if not payload:
        return RedirectResponse("/import", status_code=303)
    ImportService(session).commit(
        payload["preview"],
        account_name=account_name.strip(),
        broker=broker,
        source_path=Path(payload["path"]),
    )
    return RedirectResponse("/holdings", status_code=303)


@router.post("/holdings/manual")
async def manual_add(
    request: Request,
    session: Session = Depends(db_session),
    account_name: str = Form(...),
    symbol: str = Form(...),
    exchange: str = Form("NSE"),
    quantity: str = Form(...),
    avg_cost: str = Form(...),
    last_price: str = Form(""),
    company_name: str = Form(""),
) -> RedirectResponse:
    qty = to_decimal(quantity)
    avg = to_decimal(avg_cost)
    if qty is None or avg is None:
        return RedirectResponse("/holdings", status_code=303)
    ImportService(session).add_manual(
        account_name.strip(),
        MappedRow(
            symbol=symbol,
            exchange=exchange,
            company_name=company_name or None,
            quantity=qty,
            avg_cost=avg,
            last_price=to_decimal(last_price),
        ),
    )
    return RedirectResponse("/holdings", status_code=303)


@router.post("/holdings/{holding_id}/delete")
def delete_holding_form(
    holding_id: int, session: Session = Depends(db_session)
) -> RedirectResponse:
    repo = HoldingRepo(session)
    holding = repo.get(holding_id)
    if holding:
        repo.delete(holding)
    return RedirectResponse("/holdings", status_code=303)


@router.post("/holdings/{holding_id}/edit")
async def edit_holding_form(
    holding_id: int,
    session: Session = Depends(db_session),
    quantity: str = Form(...),
    avg_cost: str = Form(...),
    last_price: str = Form(""),
    notes: str = Form(""),
) -> RedirectResponse:
    repo = HoldingRepo(session)
    holding = repo.get(holding_id)
    if holding:
        repo.update_manual(
            holding,
            quantity=to_decimal(quantity) or holding.quantity,
            avg_cost=to_decimal(avg_cost) or holding.avg_cost,
            last_price=to_decimal(last_price),
            notes=notes or None,
        )
    return RedirectResponse(f"/holdings/{holding_id}", status_code=303)


@router.get("/risk", response_class=HTMLResponse)
def risk_page(request: Request, session: Session = Depends(db_session)) -> HTMLResponse:
    repo = HoldingRepo(session)
    rows = repo.list()
    views = _with_sparks(session, [repo.to_view(row) for row in rows])
    ranked = sorted(views, key=lambda item: abs(float(item.beta or 0)), reverse=True)
    return templates.TemplateResponse(
        request,
        "risk.html",
        _ctx(
            request,
            session,
            active="risk",
            book=repo.summary(rows),
            holdings=ranked,
            risk_chart=risk_chart_html(BOOK, RiskRepo(session).points(BOOK)),
        ),
    )


@router.post("/risk/refresh")
def refresh_risk(
    request: Request,
    session: Session = Depends(db_session),
    next_url: str = Form("/risk"),
    force: str = Form(""),
) -> RedirectResponse:
    RiskService(session).compute(force=bool(force))
    target = next_url if next_url.startswith("/") else "/risk"
    return RedirectResponse(target, status_code=303)


@router.post("/eod/refresh")
def refresh_eod(
    request: Request,
    session: Session = Depends(db_session),
    next_url: str = Form("/"),
    force: str = Form(""),
) -> RedirectResponse:
    EodService(session).run(force=bool(force), fetch=True)
    target = next_url if next_url.startswith("/") else "/"
    return RedirectResponse(target, status_code=303)


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request, session: Session = Depends(db_session)) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "alerts.html", _ctx(request, session, active="alerts")
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: Session = Depends(db_session)) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "settings.html",
        _ctx(request, session, active="settings", settings=settings, db_path=str(settings.db_path)),
    )


@router.post("/settings/seed")
def load_demo() -> RedirectResponse:
    seed_demo(reset=False)
    return RedirectResponse("/", status_code=303)


@router.post("/accounts")
async def create_account(
    session: Session = Depends(db_session),
    name: str = Form(...),
    broker: str = Form("generic"),
    client_id: str = Form(""),
) -> RedirectResponse:
    AccountRepo(session).create(name.strip(), broker=broker, client_id=client_id or None)
    return RedirectResponse("/settings", status_code=303)
