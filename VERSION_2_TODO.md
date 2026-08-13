# MERIDIAN — Version 2 TODO

**Status: IN PROGRESS (implemented in `portfolioV2/`, isolated from v1)**

Product intent is locked in **`VERSION_2_DECISIONS.md`**. Exploration map: **`VERSION_2_EXPLORATION.md`**.  
App: `portfolioV2/` · package `meridian_v2` · DB `~/MeridianV2/meridian_v2.db` · port 8766.

---

## Version 2 scope

### 1. Pre-trade watchlist — candidates before buy/sell

- [x] Track **new stocks** not yet in the portfolio (research / candidate list)
- [x] Track **commodities** (gold, silver, crude, copper, etc.) with **MCX-oriented** marks
- [x] **Soft cap ~50** active watch names; warn at cap
- [x] **Archived watch** state: retained, **not scored daily**
- [x] Separate Watch / Research book from the live holdings book
- [x] Score **active** names with multi-factor / regime / news (v2-owned factors; no v1 import)
- [x] “Consider for entry / avoid / wait” notes — **advisor only**, no order placement
- [x] Link items to catalysts (results, events, technical levels)

### 2. Commodities — MCX roll machinery

- [x] **Roll machinery** for near/next contracts and continuous series rules
- [x] Clear UI labelling: contract vs continuous vs roll date
- [x] Tests for roll gaps and mark continuity
- [x] Still **no** commodity order execution

### 3. Money-market, FX context, and hedge *review* prompts

- [x] Track USDINR and majors (USD, EUR, JPY, …) as **context**
- [x] Show FX moves with portfolio / commodity risk (correlation / regime)
- [x] **Hedge review reminders** allowed with **careful wording** (review / consider / note — never “you must hedge” or execute language)
- [x] Always show **why** (exposure, move, regime) next to a reminder
- [x] **No** FX or hedge order routing

### 4. Trade algorithms → signals (not execution)

- [x] Signal-only algorithms: Buy / Sell / Hold *suggestions*
- [x] Candidate families (minimal set for v2):
  - Trend / MA crossover with regime filter
  - Mean-reversion with volatility bands
  - Breakout + volume confirmation
  - Multi-factor score threshold + regime gate
  - Cross-asset rules (equity tempered by USDINR or commodity stress)
- [x] Every signal: rule name, parameters, timestamp/timeframe, strength, human reason
- [x] **Portfolio-relevant signals:** **Explicit Acknowledge** (Accept / Dismiss / Snooze)
- [x] After ack: optional **intended-trade note** (side, size intent, reason, links to signal/regime/scores)
- [x] Watchlist-only noise may stay log-only until promoted
- [x] Signal log + paper backtest *report* hooks
- [x] **Hard rule:** no place / route / auto-execute orders

### 5. Post-mortem spine (primary success metric)

- [x] Intended-trade journal linked to acks and outcomes
- [x] Hooks to compare desk state (regime, scores, news) on intent day vs later result
- [x] Secondary goal: friction that reduces impulsive live-book adds without prior watch/ack

### 6. Supporting work

- [x] Data providers for MCX-style commodity series + FX, cache and fallbacks
- [x] Schema: watchlist (active/archived), roll metadata, signal events, intended trades, filter state as needed
- [x] UI: Watchlist, pending-ack queue, journal, FX/commodity context, hedge review strip
- [x] Config flags so v2 modules stay disabled until enabled

---

## Also shipped from the exploration extras

- Weekly / multi-timeframe fields on the tape + daily/weekly alignment in trend signals
- Peer / sector relative score on the Watch page
- Scenario / stress stub on Command (`If index −5%…`)
- User-defined alert policies (`score_below`, `usdinr_move`, `regime_is`)
- Research notebook export (`GET /export.md` or `python -m meridian_v2 export`)
- Read-only v1 holdings snapshot → V2 watch (`python -m meridian_v2 import-v1`)
- Equity/commodity CSV import (`python -m meridian_v2 import-csv`)
- Regime sensors from USDINR + GOLD vs SMA (not a v1 import)

Commodity free tape remains an **international proxy** with a `proxy` quality flag until a native MCX feed exists. That is labelled, never hidden as an equity ticker.

---

## Explicit non-goals for Version 2

- Broker order placement / SmartAPI / Kite (or other) **live** order APIs
- Auto-execution, bracket orders, unattended strategies
- Guaranteed real-time tick data or paid terminal as a hard dependency

---

Last updated: 2026-08-13  
Owner: Meridian desk — `sanjaymaverick-cmd/portfolio`
