# MERIDIAN — Version 2 Decisions

**Status: LOCKED (product intent) · IMPLEMENTATION FROZEN until v1 complete**

These answers close the research questions in `VERSION_2_EXPLORATION.md` and follow-on hedge/gamma questions.
Do **not** start implementation until Meridian v1 (Phases 5–8 / `ARCHITECTURE.md`) is tagged complete.

Companion files: `VERSION_2_TODO.md`, `VERSION_2_EXPLORATION.md`, `docs/v2/HEDGE_REBALANCE_SKETCH.md`.

---

## 1. Watchlist size and lifecycle

| Decision | Detail |
|----------|--------|
| **Scale** | Design for **tens** of names, not hundreds |
| **Soft cap** | **50** active watch names (configurable; warn at cap, do not silently grow) |
| **Archived watch** | Optional **archived** state: kept for history, **not scored daily**, not in EOD heavy jobs |
| **Active only** | Daily multi-factor / news / signal evaluation runs on **active** watch names only |

**Rationale:** Matches laptop EOD budgets, Screener politeness, and a readable institutional desk. Archive prevents unbounded lists without deleting research history.

---

## 2. Commodities — MCX-oriented, including roll machinery

| Decision | Detail |
|----------|--------|
| **Scope** | First-class **commodity** support because commodities are **actively traded and hedged** |
| **Market** | **MCX-oriented** continuous / near-month logic — not international proxy tiles only |
| **Roll machinery** | **Build roll handling** (near/next, roll dates, continuous series rules, clear UI labelling of contract vs continuous) |
| **Advisor rule** | Prices, signals, and hedge *reminders* only — **no** order placement |

**Rationale:** Proxy-only gold via global symbols is insufficient when the live book uses MCX-style exposure and hedges. Roll correctness is required for trustworthy marks and signals.

**Implementation note (when v2 opens):** Treat roll calendar, continuous construction, and data gaps as explicit modules with tests; never hide a rolled contract as if it were a single equity-like ticker.

---

## 3. Signals — acknowledge, then optional intended trade

| Decision | Detail |
|----------|--------|
| **Portfolio-relevant signals** | Require **Explicit Acknowledge** (Accept / Dismiss / Snooze) |
| **After acknowledge** | Optional **intended-trade note** (side, size intent, reason, link to signal + regime + scores) |
| **Watchlist / research noise** | May remain **log-only** unless promoted to portfolio-relevant |
| **Execution** | **Never** auto-send orders; journal is paper/intent only |

**Rationale:** Creates the post-mortem spine and reduces impulsive entries without building a broker.

---

## 4. FX / hedge reminders — careful wording, no execution

| Decision | Detail |
|----------|--------|
| **Context** | USDINR and major FX remain visible as **macro context** |
| **Hedge reminders** | **Allowed** as desk prompts when book/commodity exposure warrants review |
| **Wording** | Must **not** sound like firm advice or an order instruction |
| **Preferred frame** | Question / review prompt, e.g. “USDINR +Y% with open commodity hedge legs — review hedge?” |
| **Execution** | **No** FX or hedge order routing in v2 |

**Rationale:** User hedges in real life; silent context-only under-serves that. Wording and non-execution boundaries protect the advisor-only charter.

**Copy rules (binding for v2 UI):**
- Use “review”, “consider”, “note”, “open question”
- Avoid “you should hedge”, “buy USD”, “execute”, “must reduce”
- Always show the **why** (exposure, move size, regime) next to the reminder

---

## 5. Success metrics

| Priority | Metric |
|----------|--------|
| **Primary** | **Better post-mortems** — link what the desk showed, what was acknowledged, what was intended, and what happened |
| **Secondary** | **Fewer impulsive buys** — friction via ack + optional intended-trade note before new risk |

Faster research is a **by-product**, not the primary optimisation target for v2.

**Observable proxies (when measuring later):**
- Fraction of portfolio-relevant signals acknowledged within N days
- Intended-trade notes with complete reason fields
- Post-hoc reviews tagged to journal entries
- Drop in same-day watchlist → live-book promotions without prior watch/ack (heuristic)

---

## 6. Hedge book shape, dual policies, alerts, fills

Answers to gamma / hedge research questions (2026-08-13).

| # | Question | Locked answer |
|---|----------|----------------|
| 1 | Options vs futures | **Both** — long listed commodity **options** as a book **and** futures hedges |
| 2 | Inventory protection vs vol | **Both, with separate policies** — do not merge into one silent engine |
| 3 | Re-hedge cadence | **Intraday alerts** (not EOD-only) — still human ack; no auto-send |
| 4 | Actual futures fills in journal | **Yes** — record fills for scalp / hedge P&L and post-mortems |

### Policy separation (binding)

| Policy ID | Intent | Typical target | Alert character |
|-----------|--------|----------------|-----------------|
| `inventory_hedge` | Protect inventory / target hedge ratio \(h^*\) | Partial or full offset of book lots | Band / regime breach → **Hedge REVIEW** |
| `vol_harvest` (gamma scalp awareness) | Monetize **long** gamma vs implied | Often net Δ near 0 on option book | Δ drift / Γ posture → **Δ REVIEW** (scalp-aware), separate copy |

- Separate config, separate prompt streams, separate journal tags.
- UI must show **which policy** fired; never one generic “hedge” button for both intents.
- **Short gamma** never labelled as “scalping edge”; use risk **warning** language only.

### Intraday alerts (binding)

- Alerts may fire **intraday** when marks/Δ move through bands (polling or event-driven job — implementer choice).
- Each alert still requires **Explicit Acknowledge** (Accept / Dismiss / Snooze).
- **No** broker routing; cooldown / snooze still apply to limit fatigue.
- Laptop / local process constraints: document expected poll interval when implementing.

### Fills and post-mortem (binding)

- Journal supports **actual futures (and options) fills**: time, symbol/contract, side, lots, price, fees if known, link to prior intended-trade / alert.
- Enable attribution: option mark (theta/vega residual) vs futures scalp/hedge P&L between alerts.
- Primary metric remains post-mortems — fills make the loop measurable.

### Non-goals (unchanged)

- Automated gamma scalping **execution**
- Unattended intraday order placement
- OMS / SmartAPI / Kite live orders from Meridian

### Design consequences (add)

8. **Dual policy engine:** `inventory_hedge` + `vol_harvest` configs; shared exposure math (`docs/v2/HEDGE_REBALANCE_SKETCH.md`), different targets and copy.
9. **Intraday alert worker:** band checks on refreshed marks; ack queue, not execution.
10. **Fill legs on journal:** actual fills schema for post-mortem P&L.
11. **Greeks feed:** Δ/Γ on option legs when available; futures Δ = 1, Γ = 0.

---

## Design consequences (for implementers after v1)

1. **Schema:** `watch_items` with `status = active | archived`; soft cap on active; commodity symbols with roll metadata.
2. **Jobs:** Daily score/signal only `active`; archived excluded from heavy pipelines.
3. **MCX module:** Contract calendar, roll rules, continuous series, UI contract label.
4. **Signals UI:** Pending ack queue; dismiss/snooze; promote to `intended_trades`.
5. **Journal:** Intended trades + **actual fills** + outcomes hooks for post-mortems (primary metric).
6. **FX/hedge strip:** Context + carefully worded review prompts; no execution path.
7. **Dual hedge policies:** inventory vs vol-harvest; separate prompts and tags.
8. **Intraday alerts:** human-in-the-loop only.
9. **Non-goals unchanged:** No Kite/SmartAPI live orders, no unattended auto-trade, no automated scalp execution.

---

## Suggested v2 build order (still only after v1 tag)

1. Watchlist active/archived + soft cap  
2. MCX commodity marks + roll machinery (minimum viable continuous)  
3. Signal families + **acknowledge** queue  
4. Intended-trade notes → journal (**fills** schema)  
5. FX context + inventory **hedge review** prompts  
6. Exposure aggregation + threshold policy (`docs/v2/HEDGE_REBALANCE_SKETCH.md`)  
7. Option legs Δ/Γ + **vol_harvest** policy stream (separate from inventory)  
8. Intraday alert worker (ack only)  
9. Events / stress stubs / export as time allows  

---

Locked: 2026-08-13  
Hedge/gamma answers locked: 2026-08-13  
Source: product answers to exploration + gamma research questions  
Repo: `sanjaymaverick-cmd/portfolio`
