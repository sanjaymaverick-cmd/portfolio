# MERIDIAN

Institutional-grade personal equity advisor and monitor for Indian markets (NSE + BSE).

Advisor only. It does not place orders.

## Run

```powershell
cd portfolio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m meridian seed
python -m meridian
```

Desk opens at `http://127.0.0.1:8787`.

```powershell
python -m meridian import --file statement.csv --account "Core — Zerodha"
python -m meridian prices --force
python -m pytest
```

Data lives in `./data` (gitignored). Nothing leaves the machine unless you later enable optional market-data calls.

## Status

Phase 2 — local book plus a cached yfinance tape, day P&L, and OHLCV charts.
