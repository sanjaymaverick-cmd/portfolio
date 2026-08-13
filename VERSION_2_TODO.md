# MERIDIAN — Version 2 TODO

**Status: FROZEN**

Do **not** implement, scaffold, or partially build anything in this file until the current Meridian version (Phases 3–8 as defined in the active build plan / `ARCHITECTURE.md`) is complete and stable.

Product intent is locked in **`VERSION_2_DECISIONS.md`**. Exploration map: **`VERSION_2_EXPLORATION.md`**.

Version 1 remains the sole focus until tagged complete.

---

## Version 2 scope (future only)

### 1. Pre-trade watchlist — candidates before buy/sell

- [ ] Track **new stocks** not yet in the portfolio (research / candidate list)
- [ ] Track **commodities** (gold, silver, crude, copper, etc.) with **MCX-oriented** marks
- [ ] **Soft cap ~50** active watch names; warn at cap
- [ ] **Archived watch** state: retained, **not scored daily**
- [ ] Separate Watch / Research book from the live holdings book
- [ ] Score **active** names with multi-factor / regime / news (reuse v1)
- [ ] “Consider for entry / avoid / wait” notes — **advisor only**, no order placement
- [ ] Link items to catalysts (results, events, technical levels)

### 2. Commodities — MCX roll machinery

- [ ] **Roll machinery** for near/next contracts and continuous series rules
- [ ] Clear UI labelling: contract vs continuous vs roll date
- [ ] Tests for roll gaps and mark continuity
- [ ] Still **no** commodity order execution

### 3. Money-market, FX context, and hedge *review* prompts

- [ ] Track USDINR and majors (USD, EUR, JPY, …) as **context**
- [ ] Show FX moves with portfolio / commodity risk (correlation / regime)
- [ ] **Hedge review reminders** allowed with **careful wording** (review / consider / note — never “you must hedge” or execute language)
- [ ] Always show **why** (exposure, move, regime) next to a reminder
- [ ] **No** FX or hedge order routing

### 4. Trade algorithms → signals (not execution)

- [ ] Signal-only algorithms: Buy / Sell / Hold *suggestions*
- [ ] Candidate families (minimal set for v2):
  - Trend / MA crossover with regime filter
  - Mean-reversion with volatility bands
  - Breakout + volume confirmation
  - Multi-factor score threshold + regime gate (reuse v1)
  - Cross-asset rules (equity tempered by USDINR or commodity stress)
- [ ] Every signal: rule name, parameters, timestamp/timeframe, strength, human reason
- [ ] **Portfolio-relevant signals:** **Explicit Acknowledge** (Accept / Dismiss / Snooze)
- [ ] After ack: optional **intended-trade note** (side, size intent, reason, links to signal/regime/scores)
- [ ] Watchlist-only noise may stay log-only until promoted
- [ ] Signal log + paper backtest *report* hooks
- [ ] **Hard rule:** no place / route / auto-execute orders

### 5. Post-mortem spine (primary success metric)

- [ ] Intended-trade journal linked to acks and outcomes
- [ ] Hooks to compare desk state (regime, scores, news) on intent day vs later result
- [ ] Secondary goal: friction that reduces impulsive live-book adds without prior watch/ack

### 6. Supporting work

- [ ] Data providers for MCX-style commodity series + FX, cache and fallbacks
- [ ] Schema: watchlist (active/archived), roll metadata, signal events, intended trades, filter state as needed
- [ ] UI: Watchlist, pending-ack queue, journal, FX/commodity context, hedge review strip
- [ ] Config flags so v2 modules stay disabled until enabled

---

## Explicit non-goals for Version 2

- Broker order placement / SmartAPI / Kite (or other) **live** order APIs
- Auto-execution, bracket orders, unattended strategies
- Guaranteed real-time tick data or paid terminal as a hard dependency

---

## Gate

| Condition | Action |
|-----------|--------|
| Meridian v1 Phases 3–8 incomplete | **Ignore this file** |
| Meridian v1 complete and tagged | Plan v2 from this list + `VERSION_2_DECISIONS.md` |
| Someone starts coding v2 items early | Reject; re-focus on current phase |

Last updated: 2026-08-13  
Owner: Meridian desk — `sanjaymaverick-cmd/portfolio`
