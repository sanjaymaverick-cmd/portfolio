# MERIDIAN — Architecture

Local-first equity advisory desk for NSE and BSE. Advisor and monitor only — never a broker.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Research stack, Windows packaging, one language |
| API | FastAPI | Same backend for desktop now and web later |
| UI | Jinja2 + HTMX + institutional CSS | Pixel control without a Node toolchain |
| Desktop | Uvicorn on `127.0.0.1` + browser; optional `pywebview` | Zero cloud; easy PyInstaller |
| Persistence | SQLite via SQLAlchemy 2.0 | Single-file distribution |
| Config | YAML + pydantic-settings | Desk defaults + user overrides |
| Ingestion | pandas / openpyxl / pdfplumber | Broker CSV, Excel, PDF |
| Logging | loguru | Rotating local logs, graceful degradation |
| Prices | yfinance (`.NS` / `.BO` fallback), SQLite quote + bar cache | Phase 2 |
| Fundamentals | Screener.in (cached, polite) + yfinance fallback | Phase 3 |
| Later: explain | LightGBM/XGBoost surrogate + SHAP | Phase 6 |
| Charts | Plotly, custom styled | Phase 2+ |

NiceGUI/Flet were considered and rejected for the shell: their widgets fight the density and restraint this desk needs. Domain logic stays UI-agnostic so a future web client is a new folder under `meridian/ui`, not a rewrite.

## Package layout

```
meridian/
  cli.py                 launch / seed / import
  app.py                 FastAPI factory
  config.py
  domain/                money, symbols, view models
  storage/               schema, session, repositories, seed
  ingestion/             detect, map, parse CSV/XLSX/PDF
  data_providers/        yfinance tape; Screener.in; later news
  scoring/               Quality + Valuation; later regime, SHAP
  risk/                  ρ, OLS β, EWMA β, technicals
  recommendations/       (phase 6+) action + reasoning
  api/                   JSON for future web / automation
  ui/                    pages, templates, static
```

## Phases

1. **Done.** Accounts, ingestion, local book, Command / Holdings / Detail chrome.
2. **Done.** yfinance tape, `.NS`/`.BO` fallback, quote + OHLCV cache, day P&L, Plotly price chart.
3. **Done.** Screener.in fundamentals · Quality & Valuation (0–10), yfinance fallback.
4. **Done.** Technical factor · Nifty ρ · rolling OLS / recursive EWMA β · dual-axis charts.
5. Ownership + Sentiment · five-factor · regime (Calm / Elevated / Stress).
6. SHAP · recommendation copy.
7. End-of-day price–news impact (movers, filings, attribution).
8. Polish · alerts · packaging.

Page loads never block on the network. Explicit jobs: `prices`, `fundamentals`, `risk`.
