# MERIDIAN V2 — Engine Implementation Details

**Status:** Implemented as pure Python in `meridian_v2/` (no broker, no OMS).  
**Isolation:** Does not import or write to Meridian v1 (`meridian/`).

Design sources:

- `docs/v2/HEDGE_REBALANCE_SKETCH.md`
- `docs/v2/VEGA_HEDGE_SKETCH.md`
- `VERSION_2_DECISIONS.md` §6

Code:

- `meridian_v2/domain/enums.py`
- `meridian_v2/hedge/engine.py`
- `meridian_v2/vega/engine.py`
- Tests: `tests/v2/test_hedge_engine.py`, `tests/v2/test_vega_engine.py`

---

## 1. Package map

```text
meridian_v2/
  domain/enums.py          PolicyKind, RegimeLabel, AssetClass
  hedge/engine.py          inventory_hedge + vol_harvest-capable reviews
  vega/engine.py           vega_defense reviews
  config.py                MERIDIAN_V2_* env, port 8766, separate DB path
  app.py                   FastAPI /health stub
  cli.py                   python -m meridian_v2 info
```

Not yet wired: SQLite persistence of legs, UI ack queue, MCX marks, alert worker, journal fills.

---

## 2. Shared enums

```python
class PolicyKind(str, Enum):
    INVENTORY_HEDGE = "inventory_hedge"
    VOL_HARVEST = "vol_harvest"
    VEGA_DEFENSE = "vega_defense"

class RegimeLabel(str, Enum):
    CALM = "Calm"
    ELEVATED = "Elevated"
    STRESS = "Stress"
```

Every review carries `policy_kind`. Streams must stay separate in UI/journal.

---

## 3. Hedge engine (`meridian_v2.hedge`)

### 3.1 Data flow

```text
BookLeg[] + HedgeLeg[]
    → aggregate_exposure(symbol)
    → HedgeExposure (book/hedge lots & notionals, net_gamma, hedge_ratio)
    → evaluate_symbol(..., policy_kind, regime, cooldown/roll meta)
    → HedgeReview  (actionable lots, residual, copy_review, urgency)
```

`evaluate_book` maps many exposures through the same `HedgeRebalancePolicy`.

### 3.2 Leg conventions

| Field | Meaning |
|-------|---------|
| `lots` | Signed contract lots |
| `delta` | Futures default `1.0`; options use option Δ |
| `effective_lots` | `lots * delta` |
| `gamma_lots` | `lots * gamma` |
| Book notional | `lots * multiplier * mark_inr` |
| Hedge notional | `effective_lots * multiplier * mark_inr` |

**Hedge ratio**

\[
h_{\mathrm{actual}} = -\frac{\text{hedge\_notional}}{\text{book\_notional}}
\]

(None if book notional ≈ 0.)

### 3.3 Target and drift

\[
\text{target\_hedge\_notional} = -h^* \cdot \text{book\_notional}
\]

\[
\text{target\_hedge\_lots} = \frac{\text{target\_hedge\_notional}}{\text{notional\_per\_book\_lot}}
\]

\[
\text{drift} = \text{target\_hedge\_lots} - \text{hedge\_lots}
\]

**Lot snap** (toward zero by whole steps):

\[
q_{\mathrm{actionable}} = \mathrm{sign}(\mathrm{drift}) \cdot \left\lfloor \frac{|\mathrm{drift}|}{\mathrm{lot\_step}} \right\rfloor \cdot \mathrm{lot\_step}
\]

\[
\text{residual} = \mathrm{drift} - q_{\mathrm{actionable}}
\]

### 3.4 Regime scaling (defaults in code)

| Regime | `h_star_scale` | `band_scale` |
|--------|----------------|--------------|
| Calm | 1.0 | 1.3 (wider) |
| Elevated | 1.0 | 1.0 |
| Stress | 1.2 (capped at 1.0 after scale) | 0.7 (tighter) |

`effective_target` clamps \(h^*\) to \([0, 1]\).

### 3.5 Band breach

Breached when drift is material **and** (ratio off by `ratio_tol` **or** \(|\mathrm{drift}| \ge \min\_\mathrm{lots}\)), with optional min notional filter.

### 3.6 Suppress rules

| Condition | `suppress_reason` |
|-----------|-------------------|
| Symbol disabled | `symbol_disabled` |
| Within `roll_blackout_days` of roll, not breached, no gamma_flag | `roll_blackout` |
| `days_since_last_prompt < min_days_between_prompts` | `cooldown` |
| Exception | Stress **and** `gamma_flag` can bypass cooldown |

`force=True` skips suppress checks.

### 3.7 Dual policy via same math

| `policy_kind` | Copy label | Intent |
|---------------|------------|--------|
| `inventory_hedge` | **HEDGE REVIEW** | Protect inventory toward \(h^*\) |
| `vol_harvest` | **Δ REVIEW** | Flatten Δ on long-Γ book; gamma warning text |

Callers pass `policy_kind` into `aggregate_exposure` / `evaluate_symbol`. Do **not** merge streams upstream.

### 3.8 Public API

```python
from meridian_v2.hedge import (
    BookLeg, HedgeLeg, HedgeRebalancePolicy, SymbolPolicy, RebalanceBand,
    aggregate_exposure, evaluate_symbol, evaluate_book,
)
from meridian_v2.domain.enums import AssetClass, PolicyKind, RegimeLabel
```

### 3.9 Minimal usage

```python
from datetime import date
from meridian_v2.domain.enums import AssetClass, RegimeLabel
from meridian_v2.hedge import (
    BookLeg, HedgeRebalancePolicy, RebalanceBand, SymbolPolicy,
    aggregate_exposure, evaluate_symbol,
)

as_of = date.today()
book = [BookLeg("b1", "GOLD", AssetClass.COMMODITY, lots=2.0, multiplier=100.0, mark_inr=70000.0)]
exp = aggregate_exposure("GOLD", AssetClass.COMMODITY, book, [], as_of)
policy = HedgeRebalancePolicy(
    symbols=(SymbolPolicy("GOLD", h_star=0.5, band=RebalanceBand(min_lots=1.0), lot_step=1.0),)
)
review = evaluate_symbol(exp, policy.symbols[0], policy, RegimeLabel.CALM)
# review.drift_lots_actionable, review.copy_review, review.urgency
```

---

## 4. Vega engine (`meridian_v2.vega`)

### 4.1 Data flow

```text
OptionGreekLeg[]
    → aggregate_vega(symbol)
    → VegaExposure (net_vega, net_delta_lots, net_gamma, iv_ref)
    → evaluate_vega(policy, hedge_vega_per_lot, stress?)
    → VegaReview (opt lots, residual ν, futures Δ clean-up, copy)
```

### 4.2 Units

| Quantity | Unit |
|----------|------|
| `vega_per_lot` | ₹ P&L per **+1.00** vol point per lot |
| `net_vega` | Sum `lots * vega_per_lot` |
| `vega_limit` | Max \|ν\| |
| `nu_star` | Target ν when defending (default 0) |

### 4.3 Utilization and action

\[
\mathrm{util} = \frac{|\nu|}{\mathrm{limit}}
\]

- **Within limit and below warn** → no actionable option lots  
- **Over limit (or `force`)** → size options toward `nu_star`  
- **Warn only** → urgency/copy may fire; actionable lots still require over/force in current code  

\[
q_{\mathrm{opt,raw}} = \frac{\nu^* - \nu}{\mathrm{hedge\_vega\_per\_lot}}
\]

Snap with `lot_step`. Residual:

\[
\nu_{\mathrm{residual}} = \nu + q_{\mathrm{opt}} \cdot \mathrm{hedge\_vega\_per\_lot}
\]

Futures clean-up (does **not** change vega):

\[
q_{\mathrm{fut}} = -\big(\Delta_{\mathrm{net}} + q_{\mathrm{opt}} \cdot \mathrm{hedge\_delta}\big)
\]

then snap.

### 4.4 Urgency

| Condition | Urgency |
|-----------|---------|
| Over limit + Stress | `elevated` |
| Over limit or warn | `review` |
| Else | `none` |

Copy always includes **“VEGA REVIEW — not an order”** and `[vega_defense]`.

### 4.5 Public API

```python
from meridian_v2.vega import (
    OptionGreekLeg, VegaPolicy, aggregate_vega, evaluate_vega,
)
```

### 4.6 Minimal usage

```python
from datetime import date
from meridian_v2.vega import OptionGreekLeg, VegaPolicy, aggregate_vega, evaluate_vega

as_of = date.today()
legs = [OptionGreekLeg("1", "GOLD", "CE", lots=4.0, multiplier=1.0, mark_inr=1.0,
                       delta=0.5, gamma=0.01, vega_per_lot=60_000)]
exp = aggregate_vega("GOLD", legs, as_of)
pol = VegaPolicy(symbol="GOLD", vega_limit=200_000, lot_step=1.0)
rev = evaluate_vega(exp, pol, hedge_vega_per_lot=55_000, hedge_delta=0.48)
# rev.opt_lots_actionable < 0 when long ν over limit
```

---

## 5. Integration contract (for later UI / worker)

| Stage | Owner | Contract |
|-------|--------|----------|
| Marks + Greeks | providers / manual | Populate legs; stamp `as_of` |
| Engines | pure functions | Stateless; no I/O |
| Reviews | worker/UI | Persist if `urgency != none` and not suppressed |
| Ack | human | Accept / Dismiss / Snooze |
| Intent + fills | journal | `policy_kind` required; options then futures for vega |
| Execution | **outside** Meridian | Broker terminal only |

**Stale Greeks:** callers should mute actionable lots (not yet a hard gate inside pure functions — pass `force=False` and avoid calling when stale).

---

## 6. Copy rules (implemented strings)

- Always: `not an order`
- Inventory: `HEDGE REVIEW`
- Harvest: `Δ REVIEW`
- Vega: `VEGA REVIEW`
- Closing question form: “Review whether…?”
- No “execute”, “must hedge”, “buy/sell now” as commands

---

## 7. Test matrix (current)

| Test | Expectation |
|------|-------------|
| Flat book | no breach, urgency none |
| +2 book, \(h^*=0.5\) | actionable −1 lot, breach, “not an order” |
| Long ν over limit | `opt_lots_actionable < 0` |
| Short ν over limit + stress | buy options, urgency elevated |
| Under ν limit | no actionable option lots |
| `vol_harvest` tag | policy_kind preserved; Δ REVIEW / gamma path |

```bash
pytest tests/v2 -q
```

---

## 8. Explicit non-goals (engines)

- Order routing / SmartAPI / Kite  
- Strike/expiry selection  
- Multi-leg collar optimizer  
- Shared state with v1 SQLite  
- Guaranteeing zero residual after snap  

---

## 9. Next wiring steps

1. Persist legs + reviews in `meridian_v2` SQLite (new DB only)  
2. Ack queue UI  
3. Journal intents/fills with `policy_kind`  
4. Intraday worker calling `evaluate_symbol` / `evaluate_vega`  
5. MCX contract labels on legs  

See `docs/v2/GROK_BUILD_PROMPTS.md` prompts 1–9.

---

Implemented: 2026-08-13  
Package version: `meridian_v2` `0.1.0-alpha`  
Repo: `sanjaymaverick-cmd/portfolio`
