# MERIDIAN — Version 2 Decisions

**Status: LOCKED (product intent) · IMPLEMENTATION FROZEN until v1 complete**

These answers close the research questions in `VERSION_2_EXPLORATION.md`.
Do **not** start implementation until Meridian v1 (Phases 5–8 / `ARCHITECTURE.md`) is tagged complete.

Companion files: `VERSION_2_TODO.md`, `VERSION_2_EXPLORATION.md`.

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

## Design consequences (for implementers after v1)

1. **Schema:** `watch_items` with `status = active | archived`; soft cap on active; commodity symbols with roll metadata.
2. **Jobs:** Daily score/signal only `active`; archived excluded from heavy pipelines.
3. **MCX module:** Contract calendar, roll rules, continuous series, UI contract label.
4. **Signals UI:** Pending ack queue; dismiss/snooze; promote to `intended_trades`.
5. **Journal:** Intended trades + outcomes hooks for post-mortems (primary metric).
6. **FX/hedge strip:** Context + carefully worded review prompts; no execution path.
7. **Non-goals unchanged:** No Kite/SmartAPI live orders, no unattended auto-trade.

---

## Suggested v2 build order (still only after v1 tag)

1. Watchlist active/archived + soft cap  
2. MCX commodity marks + roll machinery (minimum viable continuous)  
3. Signal families + **acknowledge** queue  
4. Intended-trade notes → journal (post-mortem spine)  
5. FX context + hedge **review** prompts (wording rules above)  
6. Alerts / events / stress stubs as time allows  

---

Locked: 2026-08-13  
Source: product answers to exploration research questions  
Repo: `sanjaymaverick-cmd/portfolio`
