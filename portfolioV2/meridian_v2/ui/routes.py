from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from meridian_v2.alerts.worker import AlertWorker, current_regime
from meridian_v2.config import get_settings
from meridian_v2.domain.models import PolicyKind
from meridian_v2.journal.service import JournalService
from meridian_v2.journal.snapshot import has_prior_watch_or_ack
from meridian_v2.mcx.roll import ui_series_label
from meridian_v2.mcx.service import McxService
from meridian_v2.risk.stress import nifty_down_scenario
from meridian_v2.scoring.service import ScoringService
from meridian_v2.signals.service import SignalService
from meridian_v2.storage.db import get_session
from meridian_v2.storage.schema import BookLegRow, FxMark, HedgeLegRow, OptionLegRow
from meridian_v2.storage.seed import seed_demo
from meridian_v2.watchlist.service import WatchlistError, WatchlistService

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
router = APIRouter()


def _ctx(request: Request, session, active: str, **extra):
    settings = get_settings()
    regime = current_regime(session, settings)
    fx = list(session.scalars(select(FxMark).order_by(FxMark.pair)))
    pending = SignalService(session).pending()
    return {
        "request": request,
        "app_name": settings.app.name,
        "subtitle": settings.app.subtitle,
        "theme": settings.app.theme,
        "active": active,
        "now": datetime.now(UTC).replace(tzinfo=None),
        "regime": {"label": regime.value, "tone": regime.value.lower()},
        "fx": fx,
        "pending_count": len(pending),
        "db_path": str(settings.db_path),
        "port": settings.app.port,
        "modules": settings.modules,
        **extra,
    }


@router.get("/")
def command(request: Request):
    session = get_session()
    try:
        pending = SignalService(session).pending()
        mcx = McxService(session).marks()
        specs = {s.symbol_key: s for s in McxService(session).specs()}
        tiles = [
            {
                "mark": m,
                "label": ui_series_label(specs[m.symbol_key]) if m.symbol_key in specs else m.symbol_key,
            }
            for m in mcx
        ]
        book = list(session.scalars(select(BookLegRow)))
        hedges = list(session.scalars(select(HedgeLegRow)))
        options = list(session.scalars(select(OptionLegRow)))
        journal = JournalService(session).intents()[:5]
        stress = nifty_down_scenario(session)
        usdinr = next((p for p in session.scalars(select(FxMark)) if p.pair == "USDINR"), None)
        usdinr_move = None
        if usdinr and usdinr.last and usdinr.prev_close:
            usdinr_move = (usdinr.last - usdinr.prev_close) / usdinr.prev_close * 100
        by_policy = {
            "inventory_hedge": [e for e in pending if e.policy_kind == PolicyKind.INVENTORY_HEDGE.value],
            "vol_harvest": [e for e in pending if e.policy_kind == PolicyKind.VOL_HARVEST.value],
            "vega_defense": [e for e in pending if e.policy_kind == PolicyKind.VEGA_DEFENSE.value],
            "signal": [e for e in pending if e.policy_kind == PolicyKind.SIGNAL.value],
            "fx_review": [e for e in pending if e.policy_kind == PolicyKind.FX_REVIEW.value],
        }
        return TEMPLATES.TemplateResponse(
            request,
            "command.html",
            _ctx(
                request,
                session,
                "command",
                pending=pending,
                by_policy=by_policy,
                tiles=tiles,
                book=book,
                hedges=hedges,
                options=options,
                journal=journal,
                stress=stress,
                usdinr_move=usdinr_move,
                commodity_notional=sum(abs(r.lots * r.multiplier * r.mark_inr) for r in book),
            ),
        )
    finally:
        session.close()


@router.get("/watch")
def watch(request: Request):
    session = get_session()
    try:
        svc = WatchlistService(session)
        items = svc.list_items()
        scores = ScoringService(session).latest()
        book_syms = {r.symbol for r in session.scalars(select(BookLegRow))}
        sector_vals: dict[str, list[float]] = {}
        for item in items:
            row = scores.get(item.symbol)
            if item.sector and row and row.composite is not None:
                sector_vals.setdefault(item.sector, []).append(row.composite)
        rows = []
        for item in items:
            row = scores.get(item.symbol)
            peers = sector_vals.get(item.sector) or []
            rel = None
            if row and row.composite is not None and len(peers) > 1:
                rel = row.composite - (sum(peers) / len(peers))
            rows.append(
                {
                    "item": item,
                    "score": row.composite if row else None,
                    "in_book": item.symbol in book_syms,
                    "catalysts": svc.catalysts(item.id),
                    "vs_peers": rel,
                }
            )
        return TEMPLATES.TemplateResponse(
            request,
            "watch.html",
            _ctx(
                request,
                session,
                "watch",
                items=items,
                rows=rows,
                active_count=svc.active_count(),
                cap=svc.cap,
                cap_state=svc.cap_state(),
                error=request.query_params.get("error"),
            ),
        )
    finally:
        session.close()


@router.post("/watch/add")
def watch_add(
    symbol: str = Form(...),
    asset_class: str = Form("equity"),
    notes: str = Form(""),
    stance: str = Form(""),
    sector: str = Form(""),
):
    session = get_session()
    try:
        WatchlistService(session).add(symbol, asset_class, notes, stance=stance, sector=sector)
        session.commit()
        return RedirectResponse("/watch", status_code=303)
    except WatchlistError as exc:
        session.rollback()
        return RedirectResponse(f"/watch?error={exc}", status_code=303)
    finally:
        session.close()


@router.post("/watch/{item_id}/archive")
def watch_archive(item_id: int):
    session = get_session()
    try:
        WatchlistService(session).archive(item_id)
        session.commit()
        return RedirectResponse("/watch", status_code=303)
    except WatchlistError:
        session.rollback()
        return RedirectResponse("/watch", status_code=303)
    finally:
        session.close()


@router.post("/watch/{item_id}/restore")
def watch_restore(item_id: int):
    session = get_session()
    try:
        WatchlistService(session).restore(item_id)
        session.commit()
        return RedirectResponse("/watch", status_code=303)
    except WatchlistError as exc:
        session.rollback()
        return RedirectResponse(f"/watch?error={exc}", status_code=303)
    finally:
        session.close()


@router.post("/watch/{item_id}/remove")
def watch_remove(item_id: int):
    session = get_session()
    try:
        WatchlistService(session).remove(item_id)
        session.commit()
        return RedirectResponse("/watch", status_code=303)
    finally:
        session.close()


@router.get("/signals")
def signals(request: Request):
    session = get_session()
    try:
        svc = SignalService(session)
        return TEMPLATES.TemplateResponse(
            request,
            "signals.html",
            _ctx(request, session, "signals", pending=svc.pending(), recent=svc.all_recent()),
        )
    finally:
        session.close()


@router.post("/signals/{event_id}/ack")
def ack_event(
    event_id: int,
    action: str = Form(...),
    next_url: str = Form("/signals"),
    note: str = Form(""),
    side: str = Form(""),
    lots: str = Form(""),
    contract_label: str = Form(""),
):
    session = get_session()
    try:
        event = SignalService(session).ack(event_id, action)
        if action == "accept" and side and lots:
            JournalService(session).add_intent(
                policy_kind=event.policy_kind,
                symbol=event.symbol,
                side=side,
                lots=float(lots),
                reason=note or event.reason,
                regime=event.regime,
                event_id=event.id,
                contract_label=contract_label or event.contract_label,
            )
        session.commit()
        return RedirectResponse(next_url, status_code=303)
    finally:
        session.close()


@router.get("/journal")
def journal(request: Request):
    session = get_session()
    try:
        rows = JournalService(session).post_mortems()
        return TEMPLATES.TemplateResponse(
            request, "journal.html", _ctx(request, session, "journal", rows=rows)
        )
    finally:
        session.close()


@router.post("/journal/intent")
def journal_intent(
    policy_kind: str = Form(...),
    symbol: str = Form(...),
    side: str = Form(...),
    lots: float = Form(...),
    reason: str = Form(""),
    contract_label: str = Form(""),
    regime: str = Form(""),
):
    session = get_session()
    try:
        note = reason
        if not has_prior_watch_or_ack(session, symbol):
            note = (reason + " · friction: no prior watch/ack").strip(" ·")
        JournalService(session).add_intent(
            policy_kind=policy_kind,
            symbol=symbol,
            side=side,
            lots=lots,
            reason=note,
            regime=regime,
            contract_label=contract_label,
        )
        session.commit()
        return RedirectResponse("/journal", status_code=303)
    finally:
        session.close()


@router.post("/journal/fill")
def journal_fill(
    contract: str = Form(...),
    side: str = Form(...),
    lots: float = Form(...),
    price: float = Form(...),
    instrument_type: str = Form(...),
    intent_id: str = Form(""),
    symbol: str = Form(""),
    fees: float = Form(0.0),
):
    session = get_session()
    try:
        iid = int(intent_id) if intent_id.strip() else None
        JournalService(session).add_fill(
            contract=contract,
            side=side,
            lots=lots,
            price=price,
            instrument_type=instrument_type,
            intent_id=iid,
            symbol=symbol,
            fees=fees,
        )
        session.commit()
        return RedirectResponse("/journal", status_code=303)
    finally:
        session.close()


@router.get("/hedge")
def hedge_page(request: Request):
    return _policy_page(request, "hedge", PolicyKind.INVENTORY_HEDGE.value, "Inventory hedge")


@router.get("/harvest")
def harvest_page(request: Request):
    return _policy_page(request, "harvest", PolicyKind.VOL_HARVEST.value, "Vol harvest")


@router.get("/vega")
def vega_page(request: Request):
    return _policy_page(request, "vega", PolicyKind.VEGA_DEFENSE.value, "Vega defense")


def _policy_page(request: Request, active: str, policy_kind: str, title: str):
    session = get_session()
    try:
        pending = [e for e in SignalService(session).pending() if e.policy_kind == policy_kind]
        return TEMPLATES.TemplateResponse(
            request,
            "policy.html",
            _ctx(request, session, active, pending=pending, policy_kind=policy_kind, title=title),
        )
    finally:
        session.close()


@router.get("/commodities")
def commodities(request: Request):
    session = get_session()
    try:
        mcx = McxService(session)
        specs = mcx.specs()
        marks = {m.symbol_key: m for m in mcx.marks()}
        rows = [
            {
                "spec": spec,
                "mark": marks.get(spec.symbol_key),
                "label": ui_series_label(spec),
            }
            for spec in specs
        ]
        return TEMPLATES.TemplateResponse(
            request, "commodities.html", _ctx(request, session, "commodities", rows=rows)
        )
    finally:
        session.close()


@router.get("/help")
def help_page(request: Request):
    session = get_session()
    try:
        return TEMPLATES.TemplateResponse(request, "help.html", _ctx(request, session, "help"))
    finally:
        session.close()


@router.post("/desk/seed")
def desk_seed():
    session = get_session()
    try:
        seed_demo(session, reset=False)
        session.commit()
        return RedirectResponse("/", status_code=303)
    finally:
        session.close()


@router.post("/watch/{item_id}/stance")
def watch_stance(item_id: int, stance: str = Form("")):
    session = get_session()
    try:
        WatchlistService(session).set_stance(item_id, stance)
        session.commit()
        return RedirectResponse("/watch", status_code=303)
    except WatchlistError as exc:
        session.rollback()
        return RedirectResponse(f"/watch?error={exc}", status_code=303)
    finally:
        session.close()


@router.post("/watch/{item_id}/catalyst")
def watch_catalyst(
    item_id: int,
    kind: str = Form("event"),
    event_date: str = Form(""),
    level: str = Form(""),
    notes: str = Form(""),
):
    from datetime import date as date_cls

    session = get_session()
    try:
        when = date_cls.fromisoformat(event_date) if event_date else None
        lvl = float(level) if level.strip() else None
        WatchlistService(session).add_catalyst(item_id, kind, event_date=when, level=lvl, notes=notes)
        session.commit()
        return RedirectResponse("/watch", status_code=303)
    except (WatchlistError, ValueError) as exc:
        session.rollback()
        return RedirectResponse(f"/watch?error={exc}", status_code=303)
    finally:
        session.close()


@router.post("/journal/{intent_id}/outcome")
def journal_outcome(intent_id: int):
    session = get_session()
    try:
        JournalService(session).capture_outcome(intent_id)
        session.commit()
        return RedirectResponse("/journal", status_code=303)
    finally:
        session.close()


@router.get("/export.md")
def export_md():
    from meridian_v2.ui.export import research_notebook

    session = get_session()
    try:
        body = research_notebook(session)
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    finally:
        session.close()


@router.post("/desk/alerts")
def desk_alerts():
    session = get_session()
    try:
        AlertWorker(session).run_once(force=True)
        session.commit()
        return RedirectResponse("/", status_code=303)
    finally:
        session.close()
