# Advanced Hedge Strategies — Meridian V2 Research

**Status:** Version 2 research · **not for implementation until Meridian v1 is complete**  
**Charter:** Advisor-only. Structure risk with readable residuals. **No broker, no auto-execution.**

Related:

- `VERSION_2_DECISIONS.md` (dual policies, fills, MCX roll, ack)
- `docs/v2/HEDGE_REBALANCE_SKETCH.md` (Δ/Γ, inventory vs scalping matrix)
- `docs/v2/VEGA_HEDGE_SKETCH.md` (ν limits, human execution loop)
- `docs/v2/GROK_BUILD_PROMPTS.md` (separate `meridian_v2/` app)

---

## 1. Purpose

Document **advanced** hedging families beyond outright futures ratio hedges and single-Greek reviews. Advanced means:

1. Multi-leg or cross-asset structure  
2. Explicit **residual risk** after the structure  
3. Separate **policy_kind** / journal **group_id** so post-mortems stay legible  

It does **not** mean automated multi-leg execution from Meridian.

---

## 2. Layers (basic → advanced)

| Level | Control | Instruments | V2 status |
|-------|---------|-------------|-----------|
| Basic | Spot/futures Δ, ratio \(h^*\) | MCX / index futures | `inventory_hedge` sketch |
| Intermediate | Γ posture, ν limits | Listed options + futures clean-up | `vol_harvest`, `vega_defense` |
| Advanced | Path, basis, curve, cross-asset, tails | Spreads, collars, proxies, overlays | This document (templates later) |

---

## 3. Strategy families

### 3.1 Stacked Greek targets

**Idea:** Joint book targets, e.g. Δ ≈ 0, Γ in a band, \|ν\| ≤ limit.  
**Mechanics:** Options move Γ/ν; futures clean residual Δ (same pure-function spirit as existing sketches).  
**Residual:** Skew, expiry mismatch, jumps beyond diffusion.  
**Policy:** Do not emit one merged “flatten all” review — prefer per-Greek streams already defined.

### 3.2 Calendar / roll hedges

**Idea:** Offset near-month risk with deferred contracts (or the reverse) around roll.  
**Requires:** MCX roll calendar, continuous vs contract labels.  
**Residual:** Curve steepener/flattener P&L independent of spot.  
**Journal:** Always store `contract_label` on each leg.

### 3.3 Basis hedges

**Idea:** Inventory or continuous mark vs a futures month that is not a perfect match; size with regression on basis or returns.  
**Mechanics:** EWMA / OLS \(h^* = \mathrm{Cov}/\mathrm{Var}\) of inventory vs chosen contract.  
**Residual:** Basis blowout in Stress.  
**UI:** Show sample length and a simple fit quality note when available.

### 3.4 Cross-hedges

**Idea:** Proxy underlier when the exact contract is illiquid (e.g. product exposure vs gold, crude, or USDINR).  
**Mechanics:** Minimum-variance ratio; reduce \(h^*\) when rolling correlation collapses.  
**Residual:** Correlation → 0 in crisis.  
**Journal:** `proxy_symbol`, optional `r2` / lookback.

### 3.5 Collar (inventory protection)

**Idea:** Long inventory + long put + short call — downside floor, upside cap, lower net premium.  
**Greeks:** Mixed Δ/Γ/ν; short call wing adds short Γ/ν above strike.  
**Policy tag:** `inventory_collar` (not `vol_harvest`).  
**Residual:** Unhedged *above* short call; gap through put.

### 3.6 Put spread / call spread hedges

**Idea:** Defined-risk option hedge (e.g. long put + short lower put).  
**Residual:** Protection only between strikes; hole beyond the long wing.  
**UI (later):** State “effective protection band” in strike terms.

### 3.7 Risk reversal

**Idea:** Long put / short call (or reverse) without a full collar inventory frame — directional vol/skew view.  
**Tag carefully:** If used for inventory defense, still not harvest language.  
**Residual:** Large short-convexity on the short wing.

### 3.8 Regime- and event-conditioned dynamics

**Idea:** Already locked pattern — Stress tightens bands / raises \(h^*\); events tighten ν limits.  
**Extensions:** Hedge only if EWMA vol > threshold; cut cross-hedge when corr breaks; event calendar flag.  
**Execution:** Still human ack; no unattended rules engine firing orders.

### 3.9 Tail overlay (equity book)

**Idea:** Small long-put or put-spread budget vs Nifty β — crash budget in ₹, not full \(h^*=1\).  
**Policy tag:** `tail_overlay` if productized.  
**Residual:** Far-tail beyond spread; theta if held continuously.

### 3.10 FX overlay on commodities

**Idea:** INR marks embed USD; partial USDINR hedge when dollar beta dominates.  
**Copy:** REVIEW / consider only — no FX order routing from Meridian.  
**Residual:** Imperfect dollar beta, basis vs onshore INR FX.

### 3.11 Equity dispersion / pair hedges

**Idea:** Long name / short index or sector to isolate residual.  
**Mechanics:** β and residual from risk module.  
**Journal:** Pair link (`leg_group_id`) between long and short fills.

---

## 4. Static vs dynamic styles

| Style | Summary | Typical failure |
|-------|---------|-----------------|
| Static structure | Set collar/ratio, rarely touch | Gap through structure |
| Band dynamic | Rebalance only outside bands (default desk) | Bands too tight (cost) or too wide (drift) |
| Vol targeting | Scale exposure to target vol | Model vol wrong in crisis |
| CPPI-like | Hedge more as NAV falls | Path dependence, gaps |
| Insurance-only | Minimal futures, buy convexity | Theta bleed |

**Default recommendation for personal MCX/equity desk:** band-dynamic core + event tighteners — not full CPPI automation.

---

## 5. Portfolio layering pattern

```text
1. Core inventory / equity β
2. Primary hedge (futures h* or collar)
3. Greek budget (max |ν|, Γ sign policy)
4. Optional tail slice
5. Optional FX slice
```

Each layer → own `policy_kind` + ack stream + fills. Never one broker ticket mixing layers without tags.

---

## 6. Residual risk checklist (mandatory for advanced intents)

Before ack, the intended-trade (or UI) should answer:

| Question | Example answer |
|----------|----------------|
| What is hedged? | GOLD inventory Δ vs JUN future |
| What instrument(s)? | Long put 70000 / short call 76000 |
| What remains open? | Upside above 76000; basis vs continuous |
| Greek posture after? | Δ≈…, Γ sign, ν ≈ … |
| When does this fail? | Gap through puts; corr break on proxy |
| Policy tag? | `inventory_collar` |

If residual cannot be stated, the structure is not ready to journal.

---

## 7. Journal: multi-leg groups

Advanced structures need a **group** key:

```text
intent_group_id:  uuid
policy_kind:      inventory_collar | cross_hedge | tail_overlay | ...
structure_summary: short text
residual_summary:  short text
greeks_snapshot:   JSON
legs[]:            intended per contract
fills[]:           each linked to group_id + leg
```

Post-mortem joins **group → all fills → later marks**, not isolated single lots.

---

## 8. Selection guide

| Objective | Prefer |
|-----------|--------|
| Stable inventory vs spot | Futures \(h^*\) or collar |
| Cheaper downside | Put spread (accept far-tail hole) |
| Harvest realized vol | Long options + Δ bands (`vol_harvest`) |
| Survive IV spike | Avoid short ν; `vega_defense` |
| Event soon | Tighten ν; reduce short convexity; optional long puts |
| Illiquid underlier | Cross-hedge with tracked fit quality, smaller \(h^*\) |
| Crash budget on equities | Small `tail_overlay`, not full short index |

---

## 9. Mapping to existing V2 engines

| Advanced family | Primary engine | Notes |
|-----------------|----------------|-------|
| Ratio / basis / cross (futures) | `inventory_hedge` | Extend inputs with proxy series later |
| Long Γ scalping | `vol_harvest` | Futures only for Δ |
| ν budget | `vega_defense` | Option sizing + Δ clean-up |
| Collar / spreads | Future template on top of journal groups | Human picks strikes |
| Tail / FX overlay | Future policy_kind | REVIEW copy rules still bind |

Gamma **hedging** (options to move Γ) vs gamma **scalping** (futures on long Γ) remains as in `HEDGE_REBALANCE_SKETCH.md` — opposite intents, never merged labels.

---

## 10. Implementation order (after core V2 Greeks)

1. Solid `inventory_hedge` + `vol_harvest` + `vega_defense` + fills  
2. `intent_group_id` + residual text fields on journal  
3. Manual structure templates (collar, put-spread) as **forms**, not optimizers  
4. Cross-hedge ratio helper (read-only suggestion)  
5. Tail overlay and FX overlay policies if still needed  

Do not build a multi-leg OMS.

---

## 11. Non-goals

- Auto-execution of multi-leg strategies  
- Black-box “optimal hedge” without residual disclosure  
- Guaranteed neutrality under jumps  
- Short straddles marketed as inventory hedges  
- Shared live schema with Meridian v1 (V2 is a separate app)

---

## 12. Copy rules (binding)

- “Review”, “consider”, “note”, “open residual …”  
- Never “execute collar”, “must buy puts”, “auto-hedge now”  
- Always name **policy_kind** and **what remains open**

---

## 13. Test themes (when productized)

1. Multi-leg intent group lists all legs and residual text.  
2. Collar tag ≠ `vol_harvest`.  
3. Cross-hedge intent stores proxy symbol.  
4. Futures-only fill does not clear a ν limit breach.  
5. Copy on advanced review contains residual and “not an order.”

---

Drafted: 2026-08-13  
Repo: `sanjaymaverick-cmd/portfolio`
