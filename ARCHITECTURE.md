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
| Explain | XGBoost TreeExplainer + exact linear SHAP fallback | Phase 6 |
| News | Google News RSS + NSE announcements XML (stdlib) | Phase 7 |
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
  data_providers/        yfinance tape; Screener.in; Google News + NSE RSS
  scoring/               five-factor composite + regime hysteresis + news filter
  risk/                  ρ, OLS β, EWMA β, Nifty EWMA vol, Kalman trend
  recommendations/       SHAP notes + EOD price–news attribution
  api/                   JSON for future web / automation
  ui/                    pages, templates, static
```

## Phases

1. **Done.** Accounts, ingestion, local book, Command / Holdings / Detail chrome.
2. **Done.** yfinance tape, `.NS`/`.BO` fallback, quote + OHLCV cache, day P&L, Plotly price chart.
3. **Done.** Screener.in fundamentals · Quality & Valuation (0–10), yfinance fallback.
4. **Done.** Technical factor · Nifty ρ · rolling OLS / recursive EWMA β · dual-axis charts.
5. **Done.** Regime sensors + hysteresis. Ownership + Sentiment from Screener shareholding / analysis. Regime-weighted five-factor composite and actions.
6. **Done.** Regime-conditioned SHAP (TreeExplainer surrogate, linear fallback) · stored reasoning and portfolio notes.
7. **Done.** End-of-day price–news impact: movers, same-day news + filings, lexicon filter, rules (optional LLM) attribution.
8. Polish · alerts · packaging.

Page loads never block on the network. Explicit jobs: `prices`, `fundamentals`, `risk`, `regime`, `score`, `eod`.

## Phase 7 — EOD attribution

After the close (`16:15` IST on trading days) `python -m meridian eod` marks names with `|day %| ≥ 1.5` or the largest rupee contributions (cap 8). For each selected name it pulls Google News RSS and NSE `Online_announcements.xml`, then:

1. Cleans and dedupes titles.
2. Drops items that do not mention the symbol or enough of the company name.
3. Scores lexicon sentiment with negation and diminishers, tags aspect, ranks, keeps 5–8, always keeps filings.
4. Attributes via structured JSON (optional LLM at `MERIDIAN_LLM_URL`) or the rule engine. Drivers that do not cite a kept headline are dropped.
5. Persists `daily_performance`, `daily_news`, `daily_attribution`.

Command shows “Today’s movers & drivers”. Detail shows the attribution timeline. LLM is off by default.
