# MERIDIAN — Version 2 Exploration Map

**Status: RESEARCH ONLY · FROZEN**

Do **not** implement items in this file until Meridian **v1** (Phases 3–8 / current build plan in `ARCHITECTURE.md`) is complete and stable.

This document captures **what else is worth exploring for Version 2** beyond the committed pillars in `VERSION_2_TODO.md`. It is not a backlog of tickets. Prefer updating this file over starting code.

Related: `VERSION_2_TODO.md` (watchlist / commodities, FX context, signal-only algorithms).

---

## v1 boundary (do not reopen here)

v1 delivers a local Indian equity book, multi-factor advisor, regime, SHAP-style explainability, and EOD news attribution. Finish that path first.

---

## Already on the v2 board (pillars)

| Pillar | Why it belongs in v2 |
|--------|----------------------|
| Research watchlist + commodities | Pre-buy discipline without polluting the live book |
| USD / EUR / JPY (and USDINR) context | Macro overlay for risk and regime — not an FX trading desk |
| Signal engines (rules only) | Formalise why buy/sell *might* make sense, with an audit trail |

Everything below should either **extend those pillars** or stay **v3+** if it threatens scope.

---

## High-value v2 candidates (explore further)

### 1. Paper / intended-trade journal (not a broker)

- Log “I would buy/reduce X at Y for reason Z” when a signal or recommendation fires
- Track hypothetical P&L vs the actual book (learning loop)
- Still **zero** order routing

**Fits:** signals + watchlist. Low risk, high learning value.

### 2. Multi-timeframe context

- Daily desk stays primary; add weekly regime / trend (e.g. weekly bars + SMA or Kalman)
- Signal rules that require daily + weekly alignment

**Fits:** algorithms + regime reuse from v1.

### 3. Peer / sector relative value

- Rank a holding vs a sector ETF or peer set (relative strength, valuation band vs peers)
- Watchlist rule style: “cheap vs peers under Calm regime only”

**Fits:** pre-trade research. Needs careful data design (sector maps, free sources).

### 4. Event calendar as a first-class object

- Results dates, board meetings, lock-in expiries, index rebalances (as data allows)
- Watchlist and signals gated by “N days to event”

**Fits:** catalysts; stronger than ad-hoc notes.

### 5. Scenario / stress stubs (advisor, not VaR theatre)

- “If Nifty −5% and regime → Stress, estimated book hit using current βs”
- Simple, visible assumptions: portfolio β × index shock + residual haircut

**Fits:** risk desk; reuses v1 β / correlation.

### 6. Alert policy engine

- User-defined rules: score drop, regime flip, EWMA vol spike, promoter/pledge change, signal flip
- Local notifications only (OS; optional email much later)

**Fits:** v1 alert polish + v2 signals. Avoid noisy defaults.

### 7. Research notebook export

- One-click desk brief (Markdown/PDF): regime, movers attribution, top recommendations, open signals
- Personal archive — not a client-reporting product

**Fits:** institutional tone; mostly packaging of v1 outputs.

### 8. Data-quality and coverage scores

- Per symbol: bar freshness, fundamentals age, news coverage
- Dim recommendation confidence when data is stale

**Fits:** trust; small feature, large practical value.

---

## Explore lightly / keep optional

| Topic | Note |
|-------|------|
| Options / IV surface | Useful for some names; data and UX jump — prefer v3 unless only simple IV rank from free sources |
| Global equities / ADRs | Dilutes NSE/BSE focus; only if actually held |
| Tax lots / Indian tax harvest hints | Valuable but sensitive — research carefully; never present as formal tax advice |
| Portfolio optimiser (mean-variance) | Easy to overfit; if ever, constraints + regime-aware, **display-only** weights |
| Alternative data (app traffic, satellite, etc.) | Out of scope for a local personal desk |

---

## Explicitly not Version 2

Unless a later version **reopens** these non-goals:

- Live order placement (Kite / SmartAPI / other broker APIs)
- Unattended auto-trading or bracket execution
- Paid terminal feeds as a hard dependency
- “Guaranteed” alpha or black-box strategy products

See also the non-goals section in `VERSION_2_TODO.md`.

---

## Suggested exploration order (only after v1 is tagged)

1. Watchlist schema + UI (stocks first, commodities second)
2. USDINR + one commodity (e.g. gold) as context tiles
3. Two or three signal families reusing v1 scores + regime (document parameters)
4. Intended-trade journal linked to signals
5. Event calendar + alert rules
6. Stress stub on the Risk page
7. Only then: peers, weekly timeframe, export brief

This order maximises reuse of v1 (regime, factors, β, EOD attribution) and avoids building a second product.

---

## Research questions before any v2 code

1. **Watchlist size** — tens of names or hundreds? (cache and Screener rate limits)
2. **Commodities** — domestic continuous proxies vs international symbols via existing free price paths only?
3. **Signals** — discretionary confirmation (user acknowledges) vs passive log-only?
4. **FX** — context-only always, or later “hedge reminder” notes still without execution?
5. **Primary success metric** — fewer impulsive buys, better post-mortems, or faster research? Pick one.

---

## What not to do with this file

- Do not convert items into implementation PRs while Phases 5–8 are open
- Do not expand scope that competes with finishing regime, ownership/sentiment, SHAP, EOD news, or polish
- Do not treat this list as a commitment; it is a map for disciplined exploration after v1

---

Last updated: 2026-08-13  
Repo: `sanjaymaverick-cmd/portfolio`  
Companion: `VERSION_2_TODO.md`
