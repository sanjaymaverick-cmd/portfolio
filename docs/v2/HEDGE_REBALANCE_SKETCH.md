# HedgeExposure / HedgeRebalancePolicy — Design Sketch

**Status:** Version 2 research · **not for implementation until Meridian v1 is complete**  
**Charter:** Advisor-only. Compute drift and emit *review* suggestions. **No broker, no orders.**

Related: `VERSION_2_DECISIONS.md` (MCX roll, ack, hedge wording, post-mortems), `VERSION_2_TODO.md`, `VERSION_2_EXPLORATION.md`, `docs/v2/VEGA_HEDGE_SKETCH.md` (vega limits / defense).

---

## Goals

1. Represent **book exposure** and **existing hedges** in comparable units (lots + ₹ notional).
2. Apply a **policy** (target ratio, bands, optional regime scale) as **pure functions**.
3. Output a **HedgeReview** suitable for Explicit Acknowledge → optional intended-trade note.
4. Stay roll-aware at the data boundary (MCX continuous vs contract labels are inputs, not invented here).

---

## Units and sign conventions

| Quantity | Convention |
|----------|------------|
| `lots` | Signed. **Long inventory / long risk > 0**. Short hedge lots < 0 if they offset long inventory |
| `notional_inr` | `lots * multiplier * mark_inr` (signed with lots) |
| `hedge_ratio` | `-hedge_notional / exposure_notional` when exposure ≠ 0; 0 if flat exposure |
| Target ratio `h_star` | In `[0, 1]` = fraction of exposure notional intended to be offset by hedges |
| `delta` (per leg) | Underlier sensitivity per lot; **1.0** for futures/spot; option Δ in (−1, 1) |
| `gamma` (per leg) | ∂Δ/∂S per lot; **0** for linear futures/spot; non-zero for options |

Example: +2 lots gold inventory, −1 lot gold futures hedge → partially hedged.

---

## Data model

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class AssetClass(str, Enum):
    EQUITY = "equity"
    COMMODITY = "commodity"
    FX = "fx"


class RegimeLabel(str, Enum):
    CALM = "Calm"
    ELEVATED = "Elevated"
    STRESS = "Stress"


@dataclass(frozen=True)
class BookLeg:
    """A risk-bearing position (inventory or unhedged book risk)."""
    leg_id: str
    symbol: str                 # e.g. GOLD, CRUDEOIL, continuous key
    asset_class: AssetClass
    lots: float                 # signed
    multiplier: float           # contract multiplier
    mark_inr: float             # price in INR per underlying unit
    contract_label: str = ""    # e.g. "GOLD26APRxxxx" or "CONTINUOUS"
    delta: float = 1.0          # 1.0 linear inventory; option book legs if any
    gamma: float = 0.0          # 0.0 linear; option Γ per lot if modelled
    as_of: Optional[date] = None

    @property
    def effective_lots(self) -> float:
        return self.lots * self.delta

    @property
    def notional_inr(self) -> float:
        return self.lots * self.multiplier * self.mark_inr

    @property
    def gamma_lots(self) -> float:
        """Aggregate gamma in Δ-per-unit-S terms for this leg."""
        return self.lots * self.gamma


@dataclass(frozen=True)
class HedgeLeg:
    """An existing hedge leg (futures/options delta-equivalent lots)."""
    leg_id: str
    symbol: str                 # underlier key aligned to BookLeg.symbol where possible
    asset_class: AssetClass
    lots: float                 # signed; typically opposite sign to inventory
    multiplier: float
    mark_inr: float
    contract_label: str = ""
    delta: float = 1.0          # 1.0 for futures; option delta in (-1, 1) if used later
    gamma: float = 0.0          # 0.0 for futures; option gamma per lot if used later
    as_of: Optional[date] = None

    @property
    def effective_lots(self) -> float:
        return self.lots * self.delta

    @property
    def notional_inr(self) -> float:
        return self.effective_lots * self.multiplier * self.mark_inr

    @property
    def gamma_lots(self) -> float:
        return self.lots * self.gamma


@dataclass(frozen=True)
class HedgeExposure:
    """
    Net picture for one underlier (or one factor key).
    Built from book + hedge legs that share `symbol`.
    """
    symbol: str
    asset_class: AssetClass
    book_lots: float
    book_notional_inr: float
    hedge_lots: float           # effective lots (delta-adjusted)
    hedge_notional_inr: float
    as_of: date
    contract_notes: str = ""    # roll / continuous disclaimer for UI
    net_gamma: float = 0.0      # sum of leg gamma_lots (book + hedge)

    @property
    def net_lots(self) -> float:
        return self.book_lots + self.hedge_lots

    @property
    def net_notional_inr(self) -> float:
        return self.book_notional_inr + self.hedge_notional_inr

    @property
    def hedge_ratio(self) -> Optional[float]:
        """Fraction of book notional offset by hedges; None if no book exposure."""
        if abs(self.book_notional_inr) < 1e-6:
            return None
        # hedge_notional typically opposite sign to book → positive ratio when offsetting
        return float(-self.hedge_notional_inr / self.book_notional_inr)


@dataclass(frozen=True)
class RebalanceBand:
    """When to emit a review. Absolute lots and/or ratio points."""
    min_lots: float = 1.0           # ignore drift smaller than this many lots
    ratio_tol: float = 0.10         # |actual_ratio - h_star| tolerance
    min_notional_inr: float = 0.0   # optional ₹ floor


@dataclass(frozen=True)
class SymbolPolicy:
    symbol: str
    h_star: float                   # target hedge ratio in [0, 1]
    band: RebalanceBand = field(default_factory=RebalanceBand)
    lot_step: float = 1.0           # MCX integer lot granularity
    enabled: bool = True
    # Optional gamma awareness (v2.x — ignore if net_gamma always 0)
    gamma_warn_abs: float = 0.0     # if >0 and |net_gamma| >= this → flag in review


@dataclass(frozen=True)
class RegimeOverride:
    h_star_scale: float = 1.0       # multiply base h_star
    band_scale: float = 1.0         # multiply band widths (>1 = wider)


@dataclass(frozen=True)
class HedgeRebalancePolicy:
    symbols: tuple[SymbolPolicy, ...]
    regime_overrides: dict[RegimeLabel, RegimeOverride] = field(
        default_factory=lambda: {
            RegimeLabel.CALM: RegimeOverride(h_star_scale=1.0, band_scale=1.3),
            RegimeLabel.ELEVATED: RegimeOverride(h_star_scale=1.0, band_scale=1.0),
            RegimeLabel.STRESS: RegimeOverride(h_star_scale=1.2, band_scale=0.7),
        }
    )
    min_days_between_prompts: int = 2
    roll_blackout_days: int = 3     # suppress unless gap risk flagged externally


@dataclass(frozen=True)
class HedgeReview:
    """Advisor output — never an order."""
    symbol: str
    as_of: date
    regime: RegimeLabel
    h_star: float
    h_actual: Optional[float]
    book_lots: float
    hedge_lots: float
    drift_lots: float               # suggested signed lot change to approach target
    drift_lots_actionable: float    # snapped to lot_step
    residual_lots_after_action: float
    band_breached: bool
    urgency: str                    # "none" | "review" | "elevated"
    reason: str
    copy_review: str                # user-facing text (question form)
    suppress_reason: Optional[str] = None  # if not shown (blackout, cooldown)
    net_gamma: float = 0.0
    gamma_flag: bool = False        # |net_gamma| past policy warn threshold
```

---

## Pure functions

```python
from __future__ import annotations

import math
from datetime import date
from typing import Iterable, Optional, Sequence


def aggregate_exposure(
    symbol: str,
    asset_class: AssetClass,
    book_legs: Sequence[BookLeg],
    hedge_legs: Sequence[HedgeLeg],
    as_of: date,
    contract_notes: str = "",
) -> HedgeExposure:
    b = [x for x in book_legs if x.symbol == symbol]
    h = [x for x in hedge_legs if x.symbol == symbol]
    book_lots = sum(x.effective_lots for x in b)
    book_notional = sum(x.notional_inr for x in b)
    hedge_lots = sum(x.effective_lots for x in h)
    hedge_notional = sum(x.notional_inr for x in h)
    net_gamma = sum(x.gamma_lots for x in b) + sum(x.gamma_lots for x in h)
    return HedgeExposure(
        symbol=symbol,
        asset_class=asset_class,
        book_lots=book_lots,
        book_notional_inr=book_notional,
        hedge_lots=hedge_lots,
        hedge_notional_inr=hedge_notional,
        as_of=as_of,
        contract_notes=contract_notes,
        net_gamma=net_gamma,
    )


def effective_target(
    base_h_star: float,
    regime: RegimeLabel,
    policy: HedgeRebalancePolicy,
) -> float:
    ov = policy.regime_overrides.get(regime, RegimeOverride())
    h = base_h_star * ov.h_star_scale
    return float(min(1.0, max(0.0, h)))


def effective_band(
    band: RebalanceBand,
    regime: RegimeLabel,
    policy: HedgeRebalancePolicy,
) -> RebalanceBand:
    ov = policy.regime_overrides.get(regime, RegimeOverride())
    s = ov.band_scale
    return RebalanceBand(
        min_lots=band.min_lots * s,
        ratio_tol=band.ratio_tol * s,
        min_notional_inr=band.min_notional_inr * s,
    )


def target_hedge_lots(exposure: HedgeExposure, h_star: float) -> float:
    """
    Desired hedge effective lots so that -hedge_notional ≈ h_star * book_notional.
    Uses current mark implied by book notional / book lots when possible.
    """
    if abs(exposure.book_lots) < 1e-12:
        return 0.0
    npl = exposure.book_notional_inr / exposure.book_lots
    target_hedge_notional = -h_star * exposure.book_notional_inr
    return target_hedge_notional / npl if abs(npl) > 1e-12 else 0.0


def lot_drift(exposure: HedgeExposure, h_star: float) -> float:
    """Signed lot change to apply to hedges (positive = add long hedge lots)."""
    desired = target_hedge_lots(exposure, h_star)
    return desired - exposure.hedge_lots


def snap_lots(raw: float, lot_step: float) -> float:
    if lot_step <= 0:
        return raw
    return math.copysign(math.floor(abs(raw) / lot_step + 1e-12) * lot_step, raw)


def band_breached(
    exposure: HedgeExposure,
    h_star: float,
    band: RebalanceBand,
    drift: float,
) -> bool:
    if abs(drift) < band.min_lots:
        return False
    if band.min_notional_inr > 0:
        npl = (
            exposure.book_notional_inr / exposure.book_lots
            if abs(exposure.book_lots) > 1e-12
            else 0.0
        )
        if abs(drift * npl) < band.min_notional_inr:
            return False
    h_act = exposure.hedge_ratio
    if h_act is None:
        return abs(drift) >= band.min_lots
    return abs(h_act - h_star) > band.ratio_tol or abs(drift) >= band.min_lots


def build_review_copy(
    symbol: str,
    exposure: HedgeExposure,
    h_star: float,
    h_actual: Optional[float],
    drift_actionable: float,
    residual: float,
    regime: RegimeLabel,
    *,
    gamma_flag: bool = False,
) -> str:
    """Careful wording: review / question only — never an order instruction."""
    h_txt = f"{h_actual:.0%}" if h_actual is not None else "n/a"
    direction = "increase" if drift_actionable > 0 else "reduce" if drift_actionable < 0 else "hold"
    gamma_bit = ""
    if gamma_flag:
        sign = "long" if exposure.net_gamma > 0 else "short"
        gamma_bit = (
            f" Net gamma is {sign} ({exposure.net_gamma:+.4f}) — delta may drift "
            f"quickly if the underlier gaps; review residual risk."
        )
    return (
        f"HEDGE REVIEW — not an order. {symbol}: book {exposure.book_lots:+.2f} lots, "
        f"hedge {exposure.hedge_lots:+.2f} lots, ratio {h_txt} vs target {h_star:.0%} "
        f"({regime.value}). Model drift {drift_actionable:+.2f} lots ({direction}); "
        f"residual after step {residual:+.2f} lots."
        f"{gamma_bit} "
        f"Review whether to adjust the hedge, wait for roll, or accept residual risk?"
    )


def evaluate_symbol(
    exposure: HedgeExposure,
    symbol_policy: SymbolPolicy,
    policy: HedgeRebalancePolicy,
    regime: RegimeLabel,
    *,
    days_since_last_prompt: Optional[int] = None,
    days_to_roll: Optional[int] = None,
    force: bool = False,
) -> HedgeReview:
    if not symbol_policy.enabled:
        return _suppressed(exposure, symbol_policy, policy, regime, "symbol_disabled")

    h_star = effective_target(symbol_policy.h_star, regime, policy)
    band = effective_band(symbol_policy.band, regime, policy)
    drift = lot_drift(exposure, h_star)
    actionable = snap_lots(drift, symbol_policy.lot_step)
    residual = drift - actionable
    breached = band_breached(exposure, h_star, band, drift)
    gamma_flag = (
        symbol_policy.gamma_warn_abs > 0
        and abs(exposure.net_gamma) >= symbol_policy.gamma_warn_abs
    )

    suppress: Optional[str] = None
    if not force:
        if (
            days_to_roll is not None
            and 0 <= days_to_roll <= policy.roll_blackout_days
            and not breached
            and not gamma_flag
        ):
            suppress = "roll_blackout"
        if (
            days_since_last_prompt is not None
            and days_since_last_prompt < policy.min_days_between_prompts
            and not force
        ):
            if not (gamma_flag and regime == RegimeLabel.STRESS):
                suppress = suppress or "cooldown"

    urgency = "none"
    if (breached or gamma_flag) and suppress is None:
        urgency = "elevated" if regime == RegimeLabel.STRESS or gamma_flag else "review"

    h_act = exposure.hedge_ratio
    reason_parts = [
        f"h_star={h_star:.2f}",
        f"drift_lots={drift:.3f}",
        f"breached={breached}",
        f"regime={regime.value}",
        f"net_gamma={exposure.net_gamma:.6f}",
        f"gamma_flag={gamma_flag}",
    ]
    copy = build_review_copy(
        exposure.symbol,
        exposure,
        h_star,
        h_act,
        actionable,
        residual,
        regime,
        gamma_flag=gamma_flag,
    )

    return HedgeReview(
        symbol=exposure.symbol,
        as_of=exposure.as_of,
        regime=regime,
        h_star=h_star,
        h_actual=h_act,
        book_lots=exposure.book_lots,
        hedge_lots=exposure.hedge_lots,
        drift_lots=drift,
        drift_lots_actionable=actionable,
        residual_lots_after_action=residual,
        band_breached=breached,
        urgency=urgency if suppress is None else "none",
        reason="; ".join(reason_parts),
        copy_review=copy,
        suppress_reason=suppress,
        net_gamma=exposure.net_gamma,
        gamma_flag=gamma_flag,
    )


def _suppressed(
    exposure: HedgeExposure,
    symbol_policy: SymbolPolicy,
    policy: HedgeRebalancePolicy,
    regime: RegimeLabel,
    why: str,
) -> HedgeReview:
    h_star = effective_target(symbol_policy.h_star, regime, policy)
    return HedgeReview(
        symbol=exposure.symbol,
        as_of=exposure.as_of,
        regime=regime,
        h_star=h_star,
        h_actual=exposure.hedge_ratio,
        book_lots=exposure.book_lots,
        hedge_lots=exposure.hedge_lots,
        drift_lots=0.0,
        drift_lots_actionable=0.0,
        residual_lots_after_action=0.0,
        band_breached=False,
        urgency="none",
        reason=why,
        copy_review="",
        suppress_reason=why,
        net_gamma=exposure.net_gamma,
        gamma_flag=False,
    )


def evaluate_book(
    exposures: Iterable[HedgeExposure],
    policy: HedgeRebalancePolicy,
    regime: RegimeLabel,
    *,
    meta_by_symbol: Optional[dict[str, dict]] = None,
) -> list[HedgeReview]:
    """meta_by_symbol may include days_since_last_prompt, days_to_roll."""
    by_sym = {p.symbol: p for p in policy.symbols}
    meta_by_symbol = meta_by_symbol or {}
    out: list[HedgeReview] = []
    for exp in exposures:
        sp = by_sym.get(exp.symbol)
        if sp is None:
            continue
        m = meta_by_symbol.get(exp.symbol, {})
        out.append(
            evaluate_symbol(
                exp,
                sp,
                policy,
                regime,
                days_since_last_prompt=m.get("days_since_last_prompt"),
                days_to_roll=m.get("days_to_roll"),
                force=bool(m.get("force", False)),
            )
        )
    return out
```

---

## Gamma risk

Gamma is the **rate of change of delta** with respect to the underlier:

\[
\Gamma = \frac{\partial \Delta}{\partial S}
\]

Linear instruments (spot inventory, futures) have **Γ ≈ 0**. Options have non-zero gamma, largest near ATM and near expiry. Portfolio gamma is the sum of (lots × γ per lot) across book and hedge legs — stored here as `HedgeExposure.net_gamma`.

### Why delta-only hedging is incomplete

A book can be **delta-flat** and still make or lose money when the underlier moves:

| Net gamma | Behaviour for a discrete move in S |
|-----------|-------------------------------------|
| **Long gamma** (Γ > 0) | Delta becomes more long as S rises / more short as S falls — convex payoff; typically **pays theta** |
| **Short gamma** (Γ < 0) | Delta moves against the book in a trend or gap — concave payoff; **earns theta**, dangerous in Stress |
| **Zero gamma** | Futures-only hedges; residual risk is mainly basis, roll, and unhedged ratio — not convexity |

**Short gamma + Stress regime** is the primary warning case for a personal commodity desk that sells options as “cheap hedges.”

### Discrete re-hedge and gap risk

Between hedge reviews, delta drifts approximately:

\[
\Delta_{t+\Delta t} \approx \Delta_t + \Gamma\,\Delta S + \cdots
\]

- Large **|Γ|** → bands on delta/lots are breached faster → more reviews (or larger residuals if you do not re-hedge).
- **Gaps** (overnight MCX/global prints): one jump can move Δ a lot; band logic based on yesterday’s Δ understates risk if Γ is large.

Advisor implication: even when `band_breached` is false on *current* marks, `gamma_flag` can still surface a **review** so the human considers residual convexity risk.

### Sign and desk intuition

| Position (simplified) | Gamma | Desk note |
|-----------------------|-------|-----------|
| Long call or long put | Long Γ | Hedge Δ will need chasing; funding via theta |
| Short call or short put | Short Γ | Quiet until a move; then Δ runs away |
| Long futures / inventory | ~0 Γ | Use ratio bands only |
| Short futures hedge | ~0 Γ | Same |

### Gamma hedging vs gamma scalping

These share Greeks and band math but are **opposite intents**. Meridian must keep them as **separate policies / prompt tags** (`inventory_hedge` or explicit gamma-flatten vs `vol_harvest`).

| Dimension | **Gamma hedging** | **Gamma scalping** |
|-----------|-------------------|--------------------|
| **Goal** | Move **net Γ** toward a target (often ~0) | Keep **Γ > 0** and harvest realized vol |
| **Primary instrument** | **Options** (only they change Γ) | **Futures** (re-hedge Δ; Γ stays long) |
| **Delta role** | Clean residual Δ with futures **after** option leg | Target Δ ≈ 0 continuously via futures bands |
| **Typical book** | Short options risk, or flatten long convexity | Long straddle/strangle (or long options) |
| **P&L bet** | Reduce convexity / gap pain; may pay premium | Realized vol ≳ implied, net of theta & costs |
| **When Γ → 0** | **Success** for a flatten program | **Ends** the scalping engine |
| **Meridian policy tag** | Risk / defense review (not “scalp”) | `vol_harvest` — Δ REVIEW |
| **Copy tone** | “Net gamma short — review reducing short convexity?” | “Δ drifted from long Γ — review futures hedge?” |
| **Short Γ “scalping”** | N/A | **Invalid branding** — that is paying realized vol; use **warning** only |
| **Execution** | Ack + intended-trade only | Ack + intended-trade + **fills** for post-mortem |
| **Automated bot** | **Out of scope** | **Out of scope** |

**Rule of thumb:** If you trade **options** to change Γ, you are gamma-hedging (or opening/closing a vol book). If you trade **only futures** against a stable long-Γ options book, you are gamma-scalping mechanics.

See also: `docs/v2/VEGA_HEDGE_SKETCH.md` for **implied-vol (ν)** limits — orthogonal to both rows above.

### MVP vs later

| Phase | Gamma handling |
|-------|----------------|
| **v2 MVP (futures-first)** | `gamma = 0` on all legs; `net_gamma = 0`; no flags |
| **v2.x options** | Feed vendor/model Δ and Γ into legs; set `SymbolPolicy.gamma_warn_abs`; show gamma sentence in `copy_review` |
| **Not in scope** | Automated gamma scalping execution, continuous intraday re-hedge without ack, or guaranteed neutral books |

### Policy hooks (already in model)

- `BookLeg.gamma` / `HedgeLeg.gamma` — per-lot gamma (0 for linear).
- `HedgeExposure.net_gamma` — aggregate from `aggregate_exposure`.
- `SymbolPolicy.gamma_warn_abs` — if `> 0` and `|net_gamma| ≥ threshold` → `gamma_flag`.
- `HedgeReview.gamma_flag` / `net_gamma` — UI + journal.
- Stress: allow gamma flags to bypass soft cooldown so convexity risk is not silenced.

### Copy rules (gamma)

- State fact: “net gamma is short/long (value).”
- State consequence: “delta may drift quickly if the underlier gaps.”
- End with **review** language — never “buy/sell X to flatten gamma now” as an order.
- Never label short-gamma re-hedging as “scalping.”

### Tests (gamma)

7. Futures-only legs → `net_gamma == 0`, `gamma_flag` false.  
8. Short options with Γ such that `|net_gamma| ≥ gamma_warn_abs` → `gamma_flag` true and copy mentions gamma.  
9. Gamma flag in Stress is not suppressed solely by cooldown (per policy choice above).

---

## Integration notes (v2 only)

| Concern | Approach |
|---------|----------|
| MCX roll | `contract_label` + `contract_notes` on legs; `days_to_roll` into `evaluate_symbol` |
| Delta | `effective_lots = lots * delta`; futures delta = 1 |
| Gamma | Optional; warn-only via `gamma_flag` — does not invent trades |
| Vega | Separate module: `docs/v2/VEGA_HEDGE_SKETCH.md` |
| UI | Show `copy_review` only if `suppress_reason is None` and `urgency != "none"` |
| Ack | Treat each non-suppressed `HedgeReview` as portfolio-relevant signal |
| Journal | On ack, optional intended-trade: symbol, `drift_lots_actionable`, reason, regime, `net_gamma` |
| Equity β | Optional later: synthetic `BookLeg` from ₹ beta exposure vs Nifty futures hedge |
| Execution | **None** — no broker client imports in this module |

---

## Minimal policy example

```python
policy = HedgeRebalancePolicy(
    symbols=(
        SymbolPolicy(
            symbol="GOLD",
            h_star=0.50,
            band=RebalanceBand(min_lots=1.0, ratio_tol=0.10),
            lot_step=1.0,
            gamma_warn_abs=0.0,  # enable when option Γ feeds exist
        ),
        SymbolPolicy(
            symbol="CRUDEOIL",
            h_star=0.40,
            band=RebalanceBand(min_lots=1.0, ratio_tol=0.12),
            lot_step=1.0,
        ),
    ),
)
```

---

## Tests to write when implementing

1. Flat book → no breach, zero drift.  
2. Long inventory, zero hedge, h_star=0.5 → negative target hedge lots, breach if above band.  
3. Snap to `lot_step` leaves residual.  
4. Stress raises effective h_star and tightens band.  
5. Cooldown / roll_blackout sets `suppress_reason`.  
6. `copy_review` contains “not an order” and a question, not “execute”.  
7. Futures-only → `net_gamma == 0`.  
8. Option short gamma above threshold → `gamma_flag` and gamma sentence in copy.  
9. Stress + gamma_flag not silenced by cooldown alone.

---

## Non-goals

- Broker APIs, OMS, auto-send  
- Intraday continuous rebalancing without human ack  
- Automated gamma scalping **execution**  
- Full multi-asset mean-variance optimiser (optional later research)

---

Drafted: 2026-08-13  
Gamma section: 2026-08-13  
Gamma hedging vs scalping matrix: 2026-08-13  
Repo: `sanjaymaverick-cmd/portfolio`
