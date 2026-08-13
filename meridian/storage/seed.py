from __future__ import annotations

from decimal import Decimal

from meridian.domain.models import MappedRow
from meridian.storage.db import get_session, init_db
from meridian.storage.repositories import AccountRepo, HoldingRepo

DEMO_BOOK: list[tuple[str, str, str, str, str, str, str]] = [
    # account, broker, symbol, qty, avg, ltp, exchange
    ("Core — Zerodha", "zerodha", "RELIANCE", "80", "1245.00", "1317.00", "NSE"),
    ("Core — Zerodha", "zerodha", "HDFCBANK", "120", "690.00", "725.00", "NSE"),
    ("Core — Zerodha", "zerodha", "TCS", "35", "2480.00", "2375.00", "NSE"),
    ("Core — Zerodha", "zerodha", "INFY", "70", "1215.00", "1175.00", "NSE"),
    ("Core — Zerodha", "zerodha", "ITC", "250", "255.00", "278.50", "NSE"),
    ("Core — Zerodha", "zerodha", "BHARTIARTL", "50", "1720.00", "1939.00", "NSE"),
    ("Core — Zerodha", "zerodha", "LT", "20", "3860.00", "4070.00", "NSE"),
    ("Core — Zerodha", "zerodha", "ASIANPAINT", "20", "2910.00", "2755.00", "NSE"),
    ("Core — Zerodha", "zerodha", "SUNPHARMA", "30", "1720.00", "1932.00", "NSE"),
    ("Core — Zerodha", "zerodha", "NESTLEIND", "40", "1420.00", "1507.00", "NSE"),
    ("Satellite — Angel", "angel_one", "BAJFINANCE", "40", "1145.00", "1091.00", "NSE"),
    ("Satellite — Angel", "angel_one", "TITAN", "16", "4780.00", "5064.00", "NSE"),
    ("Satellite — Angel", "angel_one", "MARUTI", "6", "12850.00", "13905.00", "NSE"),
    ("Satellite — Angel", "angel_one", "DIXON", "8", "12100.00", "14035.00", "NSE"),
    ("Satellite — Angel", "angel_one", "POLYCAB", "10", "8750.00", "9297.00", "NSE"),
    ("Satellite — Angel", "angel_one", "IRCTC", "50", "545.00", "504.00", "NSE"),
    ("Satellite — Angel", "angel_one", "TRENT", "12", "2680.00", "2990.00", "NSE"),
]


def seed_demo(reset: bool = False) -> int:
    init_db()
    session = get_session()
    try:
        accounts = AccountRepo(session)
        holdings = HoldingRepo(session)
        if reset:
            for holding in holdings.list():
                session.delete(holding)
            session.flush()
        elif holdings.list():
            return 0
        written = 0
        for account_name, broker, symbol, qty, avg, ltp, exchange in DEMO_BOOK:
            account = accounts.create(account_name, broker=broker)
            holdings.upsert(
                account,
                MappedRow(
                    symbol=symbol,
                    exchange=exchange,
                    quantity=Decimal(qty),
                    avg_cost=Decimal(avg),
                    last_price=Decimal(ltp),
                ),
                source="demo",
            )
            written += 1
        session.commit()
        return written
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
