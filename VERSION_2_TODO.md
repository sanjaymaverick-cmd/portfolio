# MERIDIAN — Version 2 TODO

**Status: FROZEN**

Do **not** implement, scaffold, or partially build anything in this file until the current Meridian version (Phases 3–8 as defined in the active build plan / `ARCHITECTURE.md`) is complete and stable.

This list exists only to capture ideas so they are not lost. Version 1 remains the sole focus: local Indian equity book, multi-factor advisor, regime, SHAP, EOD news attribution, institutional desk UI.

---

## Version 2 scope (future only)

### 1. Pre-trade watchlist — candidates before buy/sell

- [ ] Add ability to track **new stocks** that are *not* yet in the portfolio (research / candidate list)
- [ ] Add ability to track **commodities** (e.g. gold, silver, crude, copper) as research symbols before any execution decision
- [ ] Separate “Watch / Research” book from the live holdings book
- [ ] Apply the same multi-factor scoring, regime context, and news attribution to watchlist symbols
- [ ] Explicit “consider for entry / avoid / wait” style notes — still **advisor only**, no order placement
- [ ] Link watchlist items to catalysts (results date, event, technical level)

### 2. Money-market and FX context

- [ ] Track major **money-market / FX** references for context and optional overlays:
  - USD (e.g. USDINR, DXY-style proxies as available)
  - EUR
  - JPY (Yen)
  - Other majors as data quality allows (GBP, etc.)
- [ ] Show FX moves alongside portfolio risk (correlation / regime), not as a full FX trading desk in v2 unless scoped later
- [ ] Optional display of overnight / short-rate style context if free reliable sources exist
- [ ] Keep all of this **informational** — no FX order routing

### 3. Trade algorithms → buy / sell *signals* (not execution)

- [ ] Design and implement **signal-only** algorithms that emit Buy / Sell / Hold *suggestions*
- [ ] Candidate families (research later; pick a minimal set for v2):
  - Trend / moving-average crossover with regime filter
  - Mean-reversion with volatility bands
  - Breakout + volume confirmation
  - Multi-factor score threshold + regime gate (reuse v1 scoring)
  - Simple cross-asset rules (e.g. equity signal tempered by USDINR or gold stress)
- [ ] Every signal must carry:
  - Rule name and parameters
  - Timestamp and bar/timeframe
  - Confidence or strength
  - Human-readable reason (no black box)
- [ ] Signal log and backtest *report* hooks (paper evaluation only)
- [ ] **Hard rule unchanged:** Meridian does **not** place, route, or auto-execute orders. Signals feed the advisor UI only.

### 4. Supporting work for the above (still v2)

- [ ] Data providers for commodity and FX symbols (yfinance or better free sources), with cache and fallbacks
- [ ] Schema extensions: watchlist entities, signal events, optional paper “intended trade” notes
- [ ] UI: Watchlist page, signal strip on Dashboard / Detail, FX/commodity context panel
- [ ] Config flags so v2 modules stay disabled until explicitly enabled

---

## Explicit non-goals for Version 2 (unless a later version reopens them)

- Broker order placement / SmartAPI / Kite order APIs for live trading
- Auto-execution, bracket orders, or unattended strategies
- Guaranteed real-time tick data or paid terminal feeds as a hard dependency

---

## Gate

| Condition | Action |
|-----------|--------|
| Meridian v1 Phases 3–8 incomplete | **Ignore this file** |
| Meridian v1 complete and tagged | Open Version 2 planning from this list |
| Someone starts coding v2 items early | Reject; re-focus on current phase |

Last updated: 2026-08-13  
Owner: Meridian desk — `sanjaymaverick-cmd/portfolio`
