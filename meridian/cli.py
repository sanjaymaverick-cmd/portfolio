from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from meridian.config import get_settings
from meridian.logging import setup_logging
from meridian.storage.db import init_db
from meridian.storage.seed import seed_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meridian", description="MERIDIAN equity advisory desk")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="Start the local desk (default)")
    seed = sub.add_parser("seed", help="Load the demonstration book if empty")
    seed.add_argument("--reset", action="store_true")
    imp = sub.add_parser("import", help="Import a broker statement")
    imp.add_argument("--file", required=True)
    imp.add_argument("--account", required=True)
    imp.add_argument("--broker", default=None)
    prices = sub.add_parser("prices", help="Mark the book to the yfinance tape")
    prices.add_argument("--force", action="store_true")
    funds = sub.add_parser("fundamentals", help="Refresh Screener.in Quality and Valuation")
    funds.add_argument("--force", action="store_true")
    funds.add_argument("--symbol", default=None)
    risk = sub.add_parser("risk", help="Compute technicals, ρ and β vs Nifty from the cached tape")
    risk.add_argument("--force", action="store_true")
    risk.add_argument("--symbol", default=None)
    regime = sub.add_parser("regime", help="Update Nifty/VIX sensors and the hysteresis regime label")
    regime.add_argument("--as-of", dest="as_of", default=None, help="YYYY-MM-DD")
    regime.add_argument("--no-hydrate", action="store_true")
    sub.add_parser("score", help="Recompute ownership, sentiment, composite and actions")
    eod = sub.add_parser("eod", help="After-close movers, same-day news, and attribution")
    eod.add_argument("--force", action="store_true", help="Run on weekends")
    eod.add_argument("--no-fetch", action="store_true", help="Skip RSS; attribute from stored prices only")
    eod.add_argument("--as-of", dest="as_of", default=None, help="YYYY-MM-DD")
    args = parser.parse_args(argv)

    setup_logging()
    init_db()

    if args.cmd == "seed":
        written = seed_demo(reset=args.reset)
        print(f"seeded {written} lines" if written else "book already has holdings")
        return 0
    if args.cmd == "import":
        return _import(Path(args.file), args.account, args.broker)
    if args.cmd == "prices":
        return _prices(force=args.force)
    if args.cmd == "fundamentals":
        return _fundamentals(force=args.force, symbol=args.symbol)
    if args.cmd == "risk":
        return _risk(force=args.force, symbol=args.symbol)
    if args.cmd == "regime":
        return _regime(as_of=args.as_of, hydrate=not args.no_hydrate)
    if args.cmd == "score":
        return _score()
    if args.cmd == "eod":
        return _eod(as_of=args.as_of, force=args.force, fetch=not args.no_fetch)
    return _serve()


def _import(path: Path, account: str, broker: str | None) -> int:
    from meridian.ingestion.service import ImportService
    from meridian.storage.db import get_session

    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    session = get_session()
    try:
        service = ImportService(session)
        preview = service.preview(path, broker=broker)
        accepted, rejected = service.commit(preview, account_name=account, broker=broker, source_path=path)
        session.commit()
        print(f"{preview.broker}: accepted {accepted}, rejected {rejected}")
        return 0 if accepted else 1
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _prices(*, force: bool) -> int:
    from meridian.data_providers.service import PriceService
    from meridian.storage.db import get_session

    session = get_session()
    try:
        result = PriceService(session).refresh(force=force, history=True)
        session.commit()
        if result.error:
            print(result.error, file=sys.stderr)
            return 1
        failed = f", failed {', '.join(result.failed)}" if result.failed else ""
        print(f"marked {result.marked}, skipped {result.skipped}{failed}")
        _regime(as_of=None, hydrate=False)
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _fundamentals(*, force: bool, symbol: str | None) -> int:
    from meridian.scoring.service import FundamentalService
    from meridian.storage.db import get_session

    session = get_session()
    try:
        result = FundamentalService(session).refresh(force=force, symbol=symbol)
        session.commit()
        if result.error:
            print(result.error, file=sys.stderr)
            return 1
        failed = f", failed {', '.join(result.failed)}" if result.failed else ""
        print(f"fundamentals marked {result.marked}, skipped {result.skipped}{failed}")
        return 0 if not result.failed or result.marked else 1
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _risk(*, force: bool, symbol: str | None) -> int:
    from meridian.risk.service import RiskService
    from meridian.storage.db import get_session

    session = get_session()
    try:
        result = RiskService(session).compute(force=force, symbol=symbol)
        session.commit()
        if result.error:
            print(result.error, file=sys.stderr)
            return 1
        failed = f", failed {', '.join(result.failed)}" if result.failed else ""
        print(f"risk marked {result.marked}, skipped {result.skipped}{failed} nifty={result.nifty}")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _regime(*, as_of: str | None, hydrate: bool) -> int:
    from datetime import datetime

    from meridian.scoring.regime_service import RegimeInputService
    from meridian.storage.db import get_session

    when = None
    if as_of:
        when = datetime.fromisoformat(as_of)
    session = get_session()
    try:
        result = RegimeInputService(session).run(when, hydrate=hydrate)
        session.commit()
        if result.error:
            print(result.error, file=sys.stderr)
            return 1
        print(f"regime {result.label} as_of={result.as_of.date() if result.as_of else '—'} {result.reason}")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _score() -> int:
    from meridian.scoring.composite import CompositeService
    from meridian.storage.db import get_session

    session = get_session()
    try:
        engine = CompositeService(session)
        owned = engine.rescore_ownership_sentiment()
        written = engine.recompute()
        session.commit()
        print(f"scored ownership/sentiment {owned}, composites {written} (SHAP notes written)")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _eod(*, as_of: str | None, force: bool, fetch: bool) -> int:
    from datetime import datetime

    from meridian.recommendations.eod_service import EodService
    from meridian.storage.db import get_session

    when = datetime.fromisoformat(as_of) if as_of else None
    session = get_session()
    try:
        result = EodService(session).run(when, force=force, fetch=fetch)
        session.commit()
        if result.error:
            print(result.error, file=sys.stderr)
            return 1
        if result.skipped:
            print(f"eod skipped {result.skipped} as_of={result.as_of.date() if result.as_of else '—'}")
            return 0
        names = ", ".join(result.names) if result.names else "—"
        print(
            f"eod as_of={result.as_of.date() if result.as_of else '—'} "
            f"selected {result.selected} news {result.news} attributed {result.attributed} ({names})"
        )
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _serve() -> int:
    settings = get_settings()
    url = f"http://{settings.app.host}:{settings.app.port}"
    if settings.app.open_browser:
        threading.Thread(target=_open, args=(url,), daemon=True).start()
    uvicorn.run(
        "meridian.app:create_app",
        factory=True,
        host=settings.app.host,
        port=settings.app.port,
        reload=False,
        log_level="info",
    )
    return 0


def _open(url: str) -> None:
    time.sleep(0.8)
    webbrowser.open(url)


if __name__ == "__main__":
    raise SystemExit(main())
