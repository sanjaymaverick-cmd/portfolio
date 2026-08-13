from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser

import uvicorn

from meridian_v2.config import get_settings
from meridian_v2.storage.db import get_session, init_db
from meridian_v2.storage.seed import seed_demo
from meridian_v2.watchlist.service import WatchlistError, WatchlistService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="meridian_v2",
        description="MERIDIAN V2 research & hedge-review desk (isolated from v1)",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="Start the local V2 desk (default, port 8766)")
    seed = sub.add_parser("seed", help="Load the demonstration book if empty")
    seed.add_argument("--reset", action="store_true")
    watch = sub.add_parser("watch", help="Watchlist commands")
    watch_sub = watch.add_subparsers(dest="watch_cmd")
    watch_sub.add_parser("list")
    add = watch_sub.add_parser("add")
    add.add_argument("symbol")
    add.add_argument("--class", dest="asset_class", default="equity")
    add.add_argument("--notes", default="")
    arch = watch_sub.add_parser("archive")
    arch.add_argument("id", type=int)
    rest = watch_sub.add_parser("restore")
    rest.add_argument("id", type=int)
    alerts = sub.add_parser("alerts", help="Ack-only alert worker: `alerts worker` or `alerts --once`")
    alerts.add_argument("mode", nargs="?", choices=["worker", "once"], default=None)
    alerts.add_argument("--once", action="store_true")
    alerts.add_argument("--worker", action="store_true")
    alerts.add_argument("--force", action="store_true")
    alerts.add_argument("--no-fetch", action="store_true", help="Skip tape poll; evaluate cached marks only")
    prices = sub.add_parser("prices", help="Refresh FX/commodity marks (free sources; quality-flagged)")
    prices.add_argument("--force", action="store_true")
    sub.add_parser("regime", help="Refresh desk regime sensors from tape")
    sub.add_parser("score", help="Rescore active watch names only")
    bt = sub.add_parser("backtest", help="Paper backtest report hook (no orders)")
    bt.add_argument("symbol")
    exp = sub.add_parser("export", help="Write a research notebook markdown file")
    exp.add_argument("--out", default="desk-brief.md")
    imp = sub.add_parser("import-csv", help="Import watch or book legs from CSV")
    imp.add_argument("--file", required=True)
    imp.add_argument("--kind", choices=["watch", "book"], default="watch")
    v1 = sub.add_parser("import-v1", help="Read-only snapshot of v1 holdings into the V2 watchlist")
    v1.add_argument("--db", default="")
    sub.add_parser("desktop", help="Open MERIDIAN V2 in a native window")
    args = parser.parse_args(argv)

    init_db()

    if args.cmd == "seed":
        return _seed(reset=args.reset)
    if args.cmd == "watch":
        return _watch(args)
    if args.cmd == "alerts":
        worker = args.mode == "worker" or args.worker
        once = args.mode == "once" or args.once or not worker
        return _alerts(once=once, force=args.force, poll_marks=not args.no_fetch)
    if args.cmd == "prices":
        return _prices(force=args.force)
    if args.cmd == "regime":
        return _regime()
    if args.cmd == "score":
        return _score()
    if args.cmd == "backtest":
        return _backtest(args.symbol)
    if args.cmd == "export":
        return _export(args.out)
    if args.cmd == "import-csv":
        return _import_csv(args.file, args.kind)
    if args.cmd == "import-v1":
        return _import_v1(args.db or None)
    if args.cmd == "desktop":
        return _desktop()
    return _serve()


def _seed(*, reset: bool) -> int:
    session = get_session()
    try:
        written = seed_demo(session, reset=reset)
        session.commit()
        print(f"seeded {written} watch names" if written else "desk already has data")
        return 0
    finally:
        session.close()


def _watch(args: argparse.Namespace) -> int:
    session = get_session()
    try:
        svc = WatchlistService(session)
        cmd = args.watch_cmd or "list"
        if cmd == "list":
            for item in svc.list_items():
                print(f"{item.id:4}  {item.status:8}  {item.asset_class:10}  {item.symbol}  {item.notes}")
            print(f"active {svc.active_count()}/{svc.cap}")
            return 0
        if cmd == "add":
            item = svc.add(args.symbol, args.asset_class, args.notes)
            session.commit()
            print(f"added {item.symbol} ({item.id})")
            return 0
        if cmd == "archive":
            item = svc.archive(args.id)
            session.commit()
            print(f"archived {item.symbol}")
            return 0
        if cmd == "restore":
            item = svc.restore(args.id)
            session.commit()
            print(f"restored {item.symbol}")
            return 0
        print("watch list|add|archive|restore", file=sys.stderr)
        return 2
    except WatchlistError as exc:
        session.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        session.close()


def _alerts(*, once: bool, force: bool, poll_marks: bool) -> int:
    from meridian_v2.alerts.worker import AlertWorker, run_worker

    if once:
        session = get_session()
        try:
            result = AlertWorker(session).run_once(force=force, poll_marks=poll_marks)
            session.commit()
            print(f"alerts opened {result['opened']} marked {result.get('marked', 0)}")
            return 0
        finally:
            session.close()
    print("alert worker running — ack only, no orders. Poll default 60s. Ctrl+C to stop.")
    run_worker()
    return 0


def _regime() -> int:
    from meridian_v2.risk.regime import RegimeService

    session = get_session()
    try:
        row = RegimeService(session).refresh()
        session.commit()
        print(f"regime {row.label} {row.reason}")
        return 0
    finally:
        session.close()


def _score() -> int:
    from meridian_v2.alerts.worker import current_regime
    from meridian_v2.scoring.service import ScoringService

    session = get_session()
    try:
        regime = current_regime(session, get_settings()).value
        rows = ScoringService(session).rescore(regime)
        session.commit()
        print(f"scored {len(rows)} active names ({regime})")
        return 0
    finally:
        session.close()


def _backtest(symbol: str) -> int:
    from sqlalchemy import select

    from meridian_v2.signals.backtest import run_paper_backtest
    from meridian_v2.storage.schema import PriceCache

    session = get_session()
    try:
        price = session.scalar(
            select(PriceCache).where(PriceCache.symbol == symbol.upper(), PriceCache.contract_label == "CONTINUOUS")
        )
        if price is None:
            print(f"no cached tape for {symbol}", file=sys.stderr)
            return 1
        run = run_paper_backtest(session, price)
        session.commit()
        print(run.report)
        return 0
    finally:
        session.close()


def _export(out: str) -> int:
    from pathlib import Path

    from meridian_v2.ui.export import research_notebook

    session = get_session()
    try:
        Path(out).write_text(research_notebook(session), encoding="utf-8")
        print(f"wrote {out}")
        return 0
    finally:
        session.close()


def _import_csv(path: str, kind: str) -> int:
    from pathlib import Path

    from meridian_v2.ingestion.csv_import import import_book_csv, import_watch_csv

    target = Path(path)
    if not target.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    session = get_session()
    try:
        accepted, rejected = (
            import_watch_csv(session, target) if kind == "watch" else import_book_csv(session, target)
        )
        session.commit()
        print(f"import {kind}: accepted {accepted}, rejected {rejected}")
        return 0 if accepted else 1
    finally:
        session.close()


def _import_v1(db: str | None) -> int:
    from pathlib import Path

    from meridian_v2.ingestion.v1_snapshot import import_v1_holdings_snapshot

    session = get_session()
    try:
        accepted, rejected = import_v1_holdings_snapshot(session, Path(db) if db else None)
        session.commit()
        print(f"v1 snapshot: accepted {accepted}, rejected {rejected}")
        return 0
    except Exception as exc:
        session.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        session.close()


def _prices(*, force: bool) -> int:
    from meridian_v2.data_providers.service import PriceProvider

    session = get_session()
    try:
        result = PriceProvider(session).refresh(force=force)
        session.commit()
        print(
            f"prices marked {result.get('marked', 0)} failed {result.get('failed', 0)} "
            f"applied {result.get('applied', 0)}"
        )
        return 0 if not result.get("failed") else 1
    finally:
        session.close()


def _serve(*, open_browser: bool | None = None, log_level: str = "info") -> int:
    settings = get_settings()
    url = f"http://{settings.app.host}:{settings.app.port}"
    should_open = settings.app.open_browser if open_browser is None else open_browser
    if should_open:
        threading.Thread(target=_open, args=(url,), daemon=True).start()
    uvicorn.run(
        "meridian_v2.app:create_app",
        factory=True,
        host=settings.app.host,
        port=settings.app.port,
        reload=False,
        log_level=log_level,
    )
    return 0


def _desktop() -> int:
    settings = get_settings()
    url = f"http://{settings.app.host}:{settings.app.port}"
    try:
        import webview
    except ImportError:
        print("pywebview missing — opening the browser desk. pip install 'meridian-v2[desktop]'", file=sys.stderr)
        return _serve()
    thread = threading.Thread(target=_serve, kwargs={"open_browser": False, "log_level": "warning"}, daemon=True)
    thread.start()
    time.sleep(0.8)
    webview.create_window("MERIDIAN V2", url, width=1440, height=900, min_size=(1100, 700))
    webview.start()
    return 0


def _open(url: str) -> None:
    time.sleep(0.8)
    webbrowser.open(url)


if __name__ == "__main__":
    raise SystemExit(main())
