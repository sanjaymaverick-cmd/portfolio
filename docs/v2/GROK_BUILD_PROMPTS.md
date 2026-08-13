# MERIDIAN V2 — Grok Build Prompts

**Status:** Ready for use **only after** Meridian v1 is tagged complete.  
**Hard rule:** V2 is a **different application**. Do **not** modify, replace, or overwrite the existing `meridian/` v1 package in-place.

Canonical product locks: `VERSION_2_DECISIONS.md`, `VERSION_2_TODO.md`, `VERSION_2_EXPLORATION.md`.  
Design sketches: `docs/v2/HEDGE_REBALANCE_SKETCH.md`, `docs/v2/VEGA_HEDGE_SKETCH.md`.

---

## How to use

1. Finish / tag Meridian **v1** first.
2. Create a **new** top-level package or sibling repo (recommended names below).
3. Paste **Prompt 0** once to scaffold isolation.
4. Run **Prompts 1–N** in order; each prompt is a phase.
5. Never point the agent at “refactor meridian/ into v2.”

### Recommended isolation layout

**Option A — monorepo sibling package (preferred if staying in `sanjaymaverick-cmd/portfolio`):**

```text
portfolio/
  meridian/              # V1 — DO NOT TOUCH for v2 features
  meridian_v2/           # V2 application root
  docs/v2/               # research only
  VERSION_2_*.md
```

**Option B — separate repository:** `sanjaymaverick-cmd/meridian-v2` with its own README, DB file, and Windows package name `MERIDIAN-V2`.

V2 may **read** v1 design docs and optionally **import ideas**, but must use:

- Distinct Python package name: `meridian_v2`
- Distinct SQLite path: e.g. `~/MeridianV2/meridian_v2.db` (never v1 DB path)
- Distinct CLI: `python -m meridian_v2 ...`
- Distinct desktop title / dist folder: `MERIDIAN-V2`
- Distinct ports if both run: e.g. v1 `8765`, v2 `8766`

Optional later: read-only adapter to import holdings snapshot from v1 export — not shared live schema.

---

## Prompt 0 — Scaffold separate application (mandatory first)

```text
You are building MERIDIAN V2, a brand-new local-first Indian markets desk application.

CRITICAL ISOLATION RULES:
- Create package `meridian_v2/` (or a new repo). Do NOT edit files under existing `meridian/` except docs if asked.
- Do NOT reuse or migrate the v1 SQLite database. New DB path only.
- Do NOT change v1 CLI entry points, Windows package scripts, or v1 UI.
- V2 is advisor-only: no broker order APIs (Kite, SmartAPI, etc.), no auto-execution.

Product charter:
- Personal portfolio + research desk for NSE/BSE equities AND MCX-oriented commodities.
- Watchlist (soft cap 50 active, archived not scored daily).
- Multi-factor scores, regime context (can reimplement or slim-port concepts from v1 docs).
- Signal engines with Explicit Acknowledge → optional intended-trade notes.
- Dual hedge policies: inventory_hedge vs vol_harvest (separate prompts/tags).
- Vega defense reviews (limits, sizing suggestions).
- Journal with intended trades + actual fills for post-mortems.
- Intraday alert worker: human ack only.
- FX context + carefully worded hedge REVIEW prompts (never order language).

Stack (align with institutional desk, Windows laptop):
- Python 3.11+
- FastAPI + Jinja2 + HTMX + institutional CSS (or NiceGUI only if you can match density; prefer Jinja2/HTMX like v1 for consistency)
- SQLite + SQLAlchemy 2.0
- pydantic-settings + YAML config
- yfinance / free sources for prices; MCX marks via best available free path with clear data-quality flags
- Local only: 127.0.0.1, optional pywebview later

Deliverables for this prompt only:
1. meridian_v2/ package skeleton (app factory, config, storage stub, cli)
2. README_V2.md explaining isolation from v1, how to run, DB path
3. Empty modules matching planned layout (see below)
4. pytest smoke: import meridian_v2, config loads

Planned layout:
meridian_v2/
  cli.py
  app.py
  config.py
  domain/
  storage/
  ingestion/          # optional equity PDF/CSV later; v2 can start with manual + watchlist
  data_providers/     # prices, FX, MCX stubs
  mcx/                # roll calendar, continuous series
  watchlist/
  signals/
  hedge/              # inventory + vol_harvest pure functions from docs/v2/HEDGE_REBALANCE_SKETCH.md
  vega/               # from docs/v2/VEGA_HEDGE_SKETCH.md
  journal/            # intents + fills
  alerts/             # intraday poll + ack queue
  scoring/            # optional reuse of factor concepts
  risk/               # regime sensors optional
  api/
  ui/

Read and obey: VERSION_2_DECISIONS.md, docs/v2/HEDGE_REBALANCE_SKETCH.md, docs/v2/VEGA_HEDGE_SKETCH.md.
Do not implement hedge/vega logic in Prompt 0 — skeleton only.
```

---

## Prompt 1 — Watchlist + soft cap + archive

```text
Continue MERIDIAN V2 in package meridian_v2/ only. Do not modify meridian/ (v1).

Implement Watchlist:
- Schema: watch_items (id, symbol, asset_class equity|commodity|fx, status active|archived, notes, created_at, updated_at)
- Soft cap: max 50 active (config); warn in API/UI; reject or require archive before add when at cap
- Archived: retained, excluded from daily score/signal heavy jobs
- UI: Watchlist page — add/remove, archive/restore, cap indicator
- CLI: meridian_v2 watch list|add|archive|restore

Tests: cap enforcement, archive excluded from “active” query.
No broker integration.
```

---

## Prompt 2 — MCX marks + roll machinery (MVP continuous)

```text
Continue MERIDIAN V2 in meridian_v2/ only. Do not touch v1.

Implement mcx/ module:
- Contract metadata: symbol key (GOLD, CRUDEOIL, …), near/next labels, roll date fields
- Continuous series rules documented; UI must label CONTINUOUS vs specific contract
- Price cache table for commodity bars/quotes with contract_label
- Provider interface with graceful degradation when free data is incomplete (show data-quality flag)
- Never present a rolled contract as a single equity-like ticker without label

UI: Commodity context tiles on Command/Risk strip.
Tests: roll boundary does not silently jump continuous series without metadata.
Reference: VERSION_2_DECISIONS.md §2.
```

---

## Prompt 3 — Signals + Explicit Acknowledge queue

```text
Continue MERIDIAN V2 only.

Implement signal-only engines (no execution):
- Minimal families: (1) multi-factor / score threshold + regime gate stub (2) trend/MA + regime filter stub
- Every signal: rule name, params, timestamp, strength, human reason, policy/symbol
- Portfolio-relevant signals → pending ack queue: Accept | Dismiss | Snooze
- Watchlist noise may be log-only until promoted

UI: Signals strip + Ack queue page.
Hard rule: no order placement.
Tests: ack transitions, snooze cooldown.
```

---

## Prompt 4 — Journal: intended trades + actual fills

```text
Continue MERIDIAN V2 only.

Schema:
- intended_trades: link signal/review id, policy_kind, symbol, contract_label, side, lots, reason, regime, net_greeks snapshot JSON, ref_mid/iv optional, status
- fills: time, contract, side, lots, price, fees, instrument_type option|future, intent_id

Flow: after Accept ack → optional intended-trade form → later manual fill entry linked to intent.

UI: Journal page, post-mortem view joining intent → fills → later mark snapshot if available.
Primary success metric: better post-mortems.
Tests: fill requires valid intent_id optional but preferred; list by symbol/day.
```

---

## Prompt 5 — FX context + hedge REVIEW wording

```text
Continue MERIDIAN V2 only.

- Track USDINR (+ EUR/JPY context as data allows) as macro tiles
- Hedge REVIEW prompts when exposure warrants — question form only
- Copy rules: review/consider/note — never “you should hedge”, “execute”, “buy USD”
- Always show why (exposure, move, regime)
- No FX order routing

UI: macro strip on Command.
```

---

## Prompt 6 — Inventory hedge engine (pure functions + UI)

```text
Continue MERIDIAN V2 only.

Implement hedge/ from docs/v2/HEDGE_REBALANCE_SKETCH.md:
- BookLeg, HedgeLeg, HedgeExposure, HedgeRebalancePolicy, evaluate_symbol/book
- policy_kind = inventory_hedge
- Futures-first MVP (delta=1, gamma=0)
- Emit Hedge REVIEW on band breach; Explicit Ack → optional intent
- Regime scales h_star and bands
- Roll blackout + cooldown from sketch

UI: separate “Inventory hedge” reviews — never merge with vol_harvest.
Tests: from sketch list (flat book, snap residual, stress tighter band, copy “not an order”).
No broker.
```

---

## Prompt 7 — Vol harvest (Δ reviews) + gamma flags

```text
Continue MERIDIAN V2 only.

Second policy stream policy_kind = vol_harvest:
- Long gamma book: target net Δ near 0 via futures lot bands
- Separate copy: Δ REVIEW (scalp-aware), not inventory language
- gamma_flag warnings; short gamma = risk warning only — never “scalping edge”
- Matrix: gamma hedging vs scalping from HEDGE_REBALANCE_SKETCH.md

Shared exposure math; separate config and journal tags.
Tests: under long Γ, Δ drift emits vol_harvest not inventory_hedge.
```

---

## Prompt 8 — Vega defense module

```text
Continue MERIDIAN V2 only.

Implement vega/ from docs/v2/VEGA_HEDGE_SKETCH.md:
- OptionGreekLeg, VegaExposure, evaluate_vega, VEGA REVIEW
- Limits, utilization, option lot sizing + futures Δ clean-up suggestion
- Human execution loop documented in UI help; no OMS
- Concrete examples in docs are normative for tests (long over limit sell; short stress buy; under limit no flatten)

Journal tags policy_kind=vega_defense.
Mute actionable lots if Greeks stale.
```

---

## Prompt 9 — Intraday alert worker (ack only)

```text
Continue MERIDIAN V2 only.

Background/local job:
- Poll marks on configurable interval (document default for laptop)
- Run inventory_hedge, vol_harvest, vega_defense checks
- Enqueue reviews; require Explicit Acknowledge
- Cooldown/snooze per policy_kind + symbol
- Never send orders

CLI: meridian_v2 alerts worker|--once
UI: live ack queue.
Tests: cooldown suppresses duplicate; stress + gamma can bypass soft cooldown per sketch rules.
```

---

## Prompt 10 — UI polish + packaging isolation

```text
Continue MERIDIAN V2 only.

- Institutional Command desk: regime, macro, ack queue, journal snippet, commodity labels
- Title: “MERIDIAN V2” — must not be confusable with v1 window title
- Package script scripts/package-windows-v2.ps1 → dist/MERIDIAN-V2
- README: run side-by-side with v1 on different port/DB
- Config flag modules disabled until enabled

Do not alter v1 packaging scripts.
```

---

## Master single-shot prompt (alternative)

Use only if you want one large kickoff after Prompt 0 skeleton exists:

```text
Build out MERIDIAN V2 inside meridian_v2/ exclusively. Treat sanjaymaverick-cmd/portfolio/meridian as read-only legacy.

Implement in order, committing logically:
1) Watchlist active/archived soft cap 50
2) MCX roll-aware marks MVP
3) Signals + Explicit Ack
4) Journal intents + fills
5) FX context + wording-safe hedge reviews
6) inventory_hedge pure engine + UI reviews
7) vol_harvest Δ reviews + gamma flags
8) vega_defense limits + sizing + VEGA REVIEW
9) Intraday alert worker ack-only
10) MERIDIAN-V2 packaging isolation

Obey VERSION_2_DECISIONS.md and docs/v2/*_SKETCH.md.
Advisor-only forever in v2: no Kite/SmartAPI order routing, no automated gamma scalping execution.
Primary metric: post-mortems via intent↔fill journal.
Separate policy_kind on every review and journal row.
UI copy: review/consider/note — never execute/must hedge.
```

---

## Anti-prompts (do not use)

```text
# BAD — overwrites v1
Refactor meridian/ to add commodities and hedge modules.

# BAD — shared DB
Point v2 at the existing meridian.db and migrate schema in place.

# BAD — execution
Connect SmartAPI and auto-place MCX hedges when bands breach.
```

---

Last updated: 2026-08-13  
Repo: `sanjaymaverick-cmd/portfolio`
