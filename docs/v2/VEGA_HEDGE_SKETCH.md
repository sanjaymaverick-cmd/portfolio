# Vega Exposure / Vega Defense — Design Sketch

**Status:** Version 2 research · **not for implementation until Meridian v1 is complete**  
**Charter:** Advisor-only. Measure vega, enforce limits, size optional option hedges + futures Δ clean-up. **No broker, no orders.**

Related: `docs/v2/HEDGE_REBALANCE_SKETCH.md` (Δ/Γ inventory + bands), `VERSION_2_DECISIONS.md` §6 (dual policies, fills, intraday ack).

---

## Goals

1. Aggregate **net vega** (₹ per vol point) per underlier from option legs.
2. Compare to **limits** / target `nu_star`; emit **VEGA REVIEW** when utilization or breach warrants.
3. Pure functions: option lots to move ν toward target, then futures lots to clean residual Δ.
4. Keep **separate** from `inventory_hedge` and `vol_harvest` prompt streams.

---

## Units

| Quantity | Convention |
|----------|------------|
| `vega_per_lot` | ₹ P&L for **+1.00 vol point** on one lot (e.g. 16% → 17%) |
| Leg `vega` | `lots * vega_per_lot` (signed) |
| `net_vega` | Sum over legs for one symbol key |
| `vega_limit` | Max \|ν\| in same units |
| `nu_star` | Target net vega when defending (often 0) |

Use the same vol-point definition as the Greek feed.

---

## Data model

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Sequence


class PolicyKind(str, Enum):
    INVENTORY_HEDGE = "inventory_hedge"
    VOL_HARVEST = "vol_harvest"
    VEGA_DEFENSE = "vega_defense"


@dataclass(frozen=True)
class OptionGreekLeg:
    leg_id: str
    symbol: str
    contract_label: str
    lots: float
    multiplier: float
    mark_inr: float
    delta: float
    gamma: float
    vega_per_lot: float          # ₹ per 1 vol point, per lot
    theta_per_lot: float = 0.0
    iv: Optional[float] = None
    as_of: Optional[date] = None

    @property
    def vega(self) -> float:
        return self.lots * self.vega_per_lot

    @property
    def effective_delta_lots(self) -> float:
        return self.lots * self.delta

    @property
    def gamma_lots(self) -> float:
        return self.lots * self.gamma


@dataclass(frozen=True)
class VegaExposure:
    symbol: str
    as_of: date
    net_vega: float
    net_delta_lots: float
    net_gamma: float
    leg_count: int
    iv_ref: Optional[float] = None


@dataclass(frozen=True)
class VegaPolicy:
    symbol: str
    vega_limit: float
    warn_utilization: float = 0.80
    nu_star: float = 0.0
    enabled: bool = True
    hedge_vega_per_lot: Optional[float] = None
    hedge_delta: float = 0.5
    lot_step: float = 1.0


@dataclass(frozen=True)
class VegaReview:
    symbol: str
    as_of: date
    policy_kind: PolicyKind
    net_vega: float
    vega_limit: float
    utilization: float
    over_limit: bool
    nu_star: float
    vega_drift: float
    opt_lots_raw: float
    opt_lots_actionable: float
    residual_vega: float
    futures_delta_lots: float
    urgency: str
    reason: str
    copy_review: str
    suppress_reason: Optional[str] = None
```

---

## Pure functions

```python
import math
from datetime import date
from typing import Sequence


def aggregate_vega(
    symbol: str,
    legs: Sequence[OptionGreekLeg],
    as_of: date,
) -> VegaExposure:
    use = [x for x in legs if x.symbol == symbol]
    net_vega = sum(x.vega for x in use)
    net_delta = sum(x.effective_delta_lots for x in use)
    net_gamma = sum(x.gamma_lots for x in use)
    ivs = [x.iv for x in use if x.iv is not None]
    iv_ref = sum(ivs) / len(ivs) if ivs else None
    return VegaExposure(
        symbol=symbol,
        as_of=as_of,
        net_vega=net_vega,
        net_delta_lots=net_delta,
        net_gamma=net_gamma,
        leg_count=len(use),
        iv_ref=iv_ref,
    )


def utilization(net_vega: float, limit: float) -> float:
    if limit <= 0:
        return 0.0
    return abs(net_vega) / limit


def snap_lots(raw: float, lot_step: float) -> float:
    if lot_step <= 0:
        return raw
    return math.copysign(math.floor(abs(raw) / lot_step + 1e-12) * lot_step, raw)


def option_lots_to_hit_vega_target(
    net_vega: float,
    nu_star: float,
    hedge_vega_per_lot: float,
) -> float:
    if abs(hedge_vega_per_lot) < 1e-12:
        return 0.0
    return (nu_star - net_vega) / hedge_vega_per_lot


def futures_lots_to_flatten_delta(
    net_delta_lots: float,
    option_lots: float,
    hedge_delta: float,
) -> float:
    delta_after = net_delta_lots + option_lots * hedge_delta
    return -delta_after


def build_vega_copy(
    symbol: str,
    exp: VegaExposure,
    pol: VegaPolicy,
    opt_q: float,
    fut_q: float,
    util: float,
) -> str:
    side = "long" if exp.net_vega > 0 else "short" if exp.net_vega < 0 else "flat"
    return (
        f"VEGA REVIEW — not an order. {symbol}: net vega {exp.net_vega:,.0f} ₹/vol-pt "
        f"({side}), limit {pol.vega_limit:,.0f}, utilization {util:.0%}. "
        f"Model option hedge {opt_q:+.1f} lots toward target {pol.nu_star:,.0f}; "
        f"then futures delta clean-up {fut_q:+.1f} lots. "
        f"Review reducing vol exposure, adjusting the option leg, or accepting the mark risk?"
    )


def evaluate_vega(
    exp: VegaExposure,
    pol: VegaPolicy,
    *,
    hedge_vega_per_lot: float,
    hedge_delta: float | None = None,
    regime_stress: bool = False,
    force: bool = False,
) -> VegaReview:
    if not pol.enabled:
        return VegaReview(
            symbol=exp.symbol,
            as_of=exp.as_of,
            policy_kind=PolicyKind.VEGA_DEFENSE,
            net_vega=exp.net_vega,
            vega_limit=pol.vega_limit,
            utilization=0.0,
            over_limit=False,
            nu_star=pol.nu_star,
            vega_drift=0.0,
            opt_lots_raw=0.0,
            opt_lots_actionable=0.0,
            residual_vega=exp.net_vega,
            futures_delta_lots=0.0,
            urgency="none",
            reason="disabled",
            copy_review="",
            suppress_reason="disabled",
        )

    hd = pol.hedge_delta if hedge_delta is None else hedge_delta
    hvp = (
        pol.hedge_vega_per_lot
        if pol.hedge_vega_per_lot is not None
        else hedge_vega_per_lot
    )
    util = utilization(exp.net_vega, pol.vega_limit)
    over = abs(exp.net_vega) > pol.vega_limit + 1e-6
    warn = util >= pol.warn_utilization
    target = pol.nu_star
    need_trade = over or force

    if not need_trade and not warn:
        return VegaReview(
            symbol=exp.symbol,
            as_of=exp.as_of,
            policy_kind=PolicyKind.VEGA_DEFENSE,
            net_vega=exp.net_vega,
            vega_limit=pol.vega_limit,
            utilization=util,
            over_limit=False,
            nu_star=target,
            vega_drift=exp.net_vega - target,
            opt_lots_raw=0.0,
            opt_lots_actionable=0.0,
            residual_vega=exp.net_vega,
            futures_delta_lots=0.0,
            urgency="none",
            reason="within_limit",
            copy_review="",
            suppress_reason=None,
        )

    raw = (
        option_lots_to_hit_vega_target(exp.net_vega, target, hvp)
        if need_trade
        else 0.0
    )
    actionable = snap_lots(raw, pol.lot_step)
    residual = exp.net_vega + actionable * hvp
    fut = (
        futures_lots_to_flatten_delta(exp.net_delta_lots, actionable, hd)
        if actionable
        else 0.0
    )
    fut = snap_lots(fut, pol.lot_step)

    urgency = "none"
    if over or warn:
        urgency = "elevated" if (over and regime_stress) else "review"

    copy = (
        build_vega_copy(exp.symbol, exp, pol, actionable, fut, util)
        if urgency != "none"
        else ""
    )

    return VegaReview(
        symbol=exp.symbol,
        as_of=exp.as_of,
        policy_kind=PolicyKind.VEGA_DEFENSE,
        net_vega=exp.net_vega,
        vega_limit=pol.vega_limit,
        utilization=util,
        over_limit=over,
        nu_star=target,
        vega_drift=exp.net_vega - target,
        opt_lots_raw=raw,
        opt_lots_actionable=actionable,
        residual_vega=residual,
        futures_delta_lots=fut,
        urgency=urgency,
        reason=f"util={util:.2f}; over={over}; stress={regime_stress}",
        copy_review=copy,
        suppress_reason=None,
    )
```

---

## Strategy patterns

| Pattern | Behaviour |
|---------|------------|
| **Limit defense** | Trade toward `nu_star` only when over limit (or `force`) |
| **Vol harvest under limit** | Display long vega; **do not** flatten |
| **Event tighten** | Scale `vega_limit` down in event windows; more reviews |
| **Short-vega risk** | Risk language only; prefer futures for inventory |
| **Calendar structure** | Human picks hedge contract; engine only sizes ν + residual Δ |

---

## Dual-policy wiring

```text
Greeks + marks
  → inventory_hedge   (h* bands, futures)
  → vol_harvest       (Δ bands, keep Γ>0; show ν)
  → vega_defense      (limits → VEGA REVIEW)
        → Ack → intended_trade (tag=vega_defense)
        → fills (options + futures)
        → post-mortem: νΔσ vs futures P&L
```

Do **not** merge prompt streams. Always set `policy_kind`.

---

## Execution loop (human)

Meridian **sizes and prompts**; the human **executes at the broker**. No OMS, SmartAPI, or auto-send from this module.

### Layers

| Layer | Owner | Output |
|-------|--------|--------|
| Decision / sizing | Meridian | `VegaReview` — option lots, futures Δ clean-up, copy |
| Market execution | Human + broker/terminal | Live option and futures fills |
| Record / learn | Meridian journal | Intent ↔ fills ↔ residual ν / IV |

### Step sequence

```text
1. Fresh marks + Greeks (mute actionable lots if stale)
2. aggregate_vega → evaluate_vega → VEGA REVIEW when warranted
3. Explicit Acknowledge (Accept / Dismiss / Snooze)
4. Optional intended-trade: contract label, side, lots, ref mid/IV, policy_kind=vega_defense
5. Human trades options first (changes ν), then futures (cleans Δ)
   — or accepts temporary Δ risk if legging the other way
6. Log actual fills (partials allowed; link to intent id)
7. Re-mark Greeks → residual net_vega / Δ → new review only if still offside
```

### What is executed

| Leg | Purpose |
|-----|---------|
| **Options** | Only instrument that changes **vega** (sell to cut long ν; buy to cover short ν) |
| **Futures** | Residual **delta** after option fills; does **not** hedge vega |

Strike/expiry structure is a **human** choice; pass that contract’s `hedge_vega_per_lot` into sizing before acking.

### Desk tactics (outside the app)

| Situation | Bias |
|-----------|------|
| Short ν + Stress / hard limit | Take liquidity on options; finish risk reduction |
| Long ν, soft warn, Calm | Passive or **no** trade if still under harvest mandate |
| Large size vs depth | Scale; journal each fill or average |
| Wrong tool | Futures-only cannot fix vega — do not pretend it does |

### Journal fields for execution support

**Intent (at ack):** `policy_kind`, symbol, suggested/chosen `contract_label`, `opt_lots`, `fut_lots`, `net_vega`, `iv_ref`, `ref_mid` (optional), `mark_time`, reason  

**Fill:** time, contract, side, lots, price, fees, `instrument_type` (`option` \| `future`), `intent_id`  

**After re-mark:** `net_vega_after`, `iv_after`, optional shortfall vs `ref_mid`

Simple shortfall stub (desk metric, not OMS):

\[
\text{shortfall} \approx (p_{\text{fill}} - p_{\text{ref}}) \times \text{signed qty}
\]

### Priority when multiple policies fire

| Conflict | Prefer |
|----------|--------|
| Short ν + Stress | **Vega defense** options, then Δ clean-up |
| Long ν under limit + Δ band | **Vol harvest** futures only — no vega flatten |
| Inventory \(h^*\) only | **Inventory** futures — leave ν alone |
| All three | **Separate acks**; never one mixed ticket |

### Human checklist

1. Greeks timestamp acceptable?  
2. Correct **policy** (defense vs harvest)?  
3. Contract matches intent label?  
4. Size vs depth / comfort?  
5. Options then futures (or accepted Δ risk)?  
6. Fills logged before leaving the desk?  
7. Re-mark residual ν?

### Execution non-goals

- Order routing, algo slicing, auto-retry  
- Guaranteed fill at model mid  
- Combined inventory + scalp + vega ticket without tags  

---

## Concrete execution examples

Illustrative numbers only (not live MCX quotes). Units: `vega` = ₹ per **1.00** vol point. `nu_star = 0`, `lot_step = 1`.

### Shared policy knobs

```text
symbol:           GOLD
vega_limit:       200,000 ₹/vol-pt
warn_utilization: 80%
nu_star:          0
lot_step:         1
```

---

### Example A — Long vega over limit (sell options, then futures)

**Book before**

| Item | Value |
|------|-------|
| Position | Long 4× ATM GOLD calls |
| `vega_per_lot` (book) | +60,000 |
| `net_vega` | 4 × 60,000 = **+240,000** |
| Utilization | 240k / 200k = **120%** → over limit |
| `net_delta_lots` | +2.0 (Δ≈0.50 each) |
| Regime | Calm |

**Hedge contract chosen by human**

| Item | Value |
|------|-------|
| Contract | `GOLD26MAY 72000 CE` (example label) |
| `hedge_vega_per_lot` | +55,000 (slightly different strike) |
| `hedge_delta` | 0.48 |

**Sizing**

```text
q_raw = (0 - 240_000) / 55_000 = -4.36 lots
q_opt = snap(-4.36, 1) = -4 lots          # sell 4
residual_vega = 240_000 + (-4)*55_000 = +20_000

Δ after options ≈ 2.0 + (-4)*0.48 = 2.0 - 1.92 = +0.08
q_fut = snap(-0.08, 1) = 0                 # no futures lot
```

**Review → human**

- Urgency: `review` (over limit, not Stress)
- Ack → intent: sell 4× `GOLD26MAY 72000 CE`, no futures
- Tactic: scale 2 + 2 (thin offer) or take if depth OK

**Fills (journal)**

| Time | Contract | Side | Lots | Price | Type |
|------|----------|------|------|-------|------|
| T1 | GOLD26MAY 72000 CE | Sell | 2 | 312 | option |
| T2 | GOLD26MAY 72000 CE | Sell | 2 | 309 | option |

Ref mid at ack: 315 → shortfall on sells is small (sold near mid).

**After re-mark**

| Item | Value |
|------|-------|
| `net_vega_after` | ~+20,000 (under limit) |
| Futures | none |
| Post-mortem | Limit restored; residual ν accepted |

---

### Example B — Short vega in Stress (buy options hard, then futures)

**Book before**

| Item | Value |
|------|-------|
| Position | Short 3× GOLD puts (used as “inventory hedge”) |
| `vega_per_lot` | +50,000 each long → short 3 ⇒ **net_vega = −150,000** |
| Limit | 100,000 → utilization **150%** |
| `net_delta_lots` | +1.2 (short puts ⇒ positive delta) |
| Regime | **Stress** |

**Hedge contract**

| Item | Value |
|------|-------|
| Buy | Same-expiry puts, `hedge_vega_per_lot = +50,000`, `hedge_delta = −0.40` |

**Sizing toward `nu_star = 0`**

```text
q_raw = (0 - (-150_000)) / 50_000 = +3.0
q_opt = +3                                # buy 3 puts
residual_vega = 0

Δ after options ≈ 1.2 + 3*(−0.40) = 1.2 - 1.2 = 0
q_fut = 0
```

**Human tactic**

- Urgency: `elevated`
- Level 4–5: **take** offers on puts; do not rest all day
- Intent: buy 3 puts, policy_kind=`vega_defense`

**Fills**

| Side | Lots | Note |
|------|------|------|
| Buy put | 3 | Paid offer; shortfall vs mid accepted |

**Lesson**

- Short options as inventory hedge created **short ν** — inventory should prefer futures (`inventory_hedge`) going forward
- Post-mortem tags: vega defense success; process note on policy misuse

---

### Example C — Long vega under limit + harvest Δ band (no vega trade)

**Book before**

| Item | Value |
|------|-------|
| Long straddle | `net_vega = +120,000` |
| Limit | 200,000 → util **60%** (under warn) |
| Spot rally | `net_delta_lots` drifts to **+1.4** |
| `vol_harvest` band | min 1.0 lot |

**What fires**

| Policy | Action |
|--------|--------|
| `vega_defense` | **No** VEGA REVIEW (within limit) |
| `vol_harvest` | Δ REVIEW: sell ~1 futures lot to flatten |

**Human**

- Ack **only** harvest Δ intent
- Execute **1 short gold future**
- Do **not** sell the straddle “to clean risk”

**Journal**

| Intent tag | Fill |
|------------|------|
| `vol_harvest` | Sell 1 GOLD future |

Vega unchanged by design — scalping mechanics, not vega hedge.

---

### Example D — Partial fill + residual (re-mark loop)

**Model**

```text
net_vega = +280,000  limit = 200,000
hedge_vega_per_lot = 60,000
q_raw = -4.67 → q_opt = -4
residual_vega after full fill ≈ +40,000
```

**Execution**

| Step | What happens |
|------|----------------|
| Intent | Sell 4 calls |
| Fill | Only **2** sell @ market (depth) |
| Journal | Partial: 2 of 4, link same intent_id |
| Re-mark | `net_vega ≈ +280k - 2*60k = +160k` (now under limit) |
| Decision | Accept residual; snooze further sells **or** leave working order outside Meridian |

Do not assume the unfilled 2 lots still “exist” as a hedge in the book.

---

### Example E — Wrong tool (futures-only cannot fix vega)

**Mistake**

```text
net_vega = +250,000  (over limit)
Human sells 2 GOLD futures only
```

**Result**

| Greek | Change |
|-------|--------|
| Delta | Reduced |
| **Vega** | **Unchanged** |
| Next VEGA REVIEW | Still over limit |

**Correct path**

Sell options (or option spreads) sized on `hedge_vega_per_lot`, then futures for residual Δ only.

---

### Example F — Event tighten then post-crush

**T−1 day (before event)**

```text
Effective limit = 200,000 × 0.5 = 100,000   # event_tighten
net_vega = +140,000 → over effective limit
→ VEGA REVIEW: sell options toward lower budget
```

**Human:** scale sell, fill 2 lots, ν → ~+80k before event.

**T+0 after crush**

```text
IV −3 vol points
Long ν mark-to-market ≈ −3 × 80,000 = −240,000 on options (illustrative)
```

**Tactic after crush**

- Often **Level 0–1** on further vol sales (already paid the crush)
- Journal: separate **vega_pnl_est** from any futures scalp P&L
- Do not merge with inventory fills

---

### Example G — Multi-policy same morning (separate tickets)

| Alert | Intent | Broker action |
|-------|--------|----------------|
| Inventory GOLD ratio low | `inventory_hedge` +1 future | Buy 1 future |
| Harvest Δ on silver straddle | `vol_harvest` −1 future | Sell 1 silver future |
| Crude short ν over limit | `vega_defense` buy 2 puts | Buy 2 crude puts, then Δ clean-up |

Three acks, three journal tags — never one combined “desk ticket.”

---

### Quick reference — numbers checklist

1. `util = |net_vega| / vega_limit`  
2. `q_opt = snap((nu_star - net_vega) / hedge_vega_per_lot)`  
3. `residual_vega = net_vega + q_opt * hedge_vega_per_lot`  
4. `q_fut = snap(-(net_delta + q_opt * hedge_delta))`  
5. Execute options → log fills → futures if `q_fut ≠ 0` → re-mark  

---

## Journal / post-mortem

- Intent: `policy_kind`, opt/fut lots, `net_vega` before, `iv` before  
- Fills: contract, side, lots, price, fees, link to intent  
- Stub: `vega_pnl_est ≈ net_vega_avg * (iv_after - iv_before)` in consistent units  
- Optional: execution shortfall vs ref mid at ack  

---

## Tests

1. Under limit → no actionable option lots.  
2. Long ν over limit → negative option lots (sell).  
3. Short ν over limit → positive option lots (buy).  
4. Snap leaves residual vega.  
5. Option hedge → futures Δ clean-up offsets.  
6. Copy: “not an order” + “review”.  
7. Vol harvest under limit does not call flatten.

---

## Non-goals

- Broker / OMS / auto-send  
- Guaranteed vega-neutral books  
- Automated structure selection (which strike/expiry to sell)  

---

## Implementation order (after v1)

1. Display net vega + utilization  
2. VEGA REVIEW on breach  
3. Sizing + futures clean-up suggestion  
4. Event limit scale  
5. Fill-linked IV vs futures post-mortem  

Mute actionable lots if Greeks are stale.

---

Drafted: 2026-08-13  
Execution loop section: 2026-08-13  
Concrete execution examples: 2026-08-13  
Repo: `sanjaymaverick-cmd/portfolio`
