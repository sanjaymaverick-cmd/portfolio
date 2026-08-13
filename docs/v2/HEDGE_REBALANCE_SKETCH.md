# HedgeExposure / HedgeRebalancePolicy — Design Sketch

**Status:** Version 2 research · **not for implementation until Meridian v1 is complete**  
**Charter:** Advisor-only. Compute drift and emit *review* suggestions. **No broker, no orders.**

Related: `VERSION_2_DECISIONS.md` (MCX roll, ack, hedge wording, post-mortems), `VERSION_2_TODO.md`, `VERSION_2_EXPLORATION.md`.

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
    as_of: Optional[date] = None

    @property
    def notional_inr(self) -> float:
        return self.lots * self.multiplier * self.mark_inr


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
    delta: float = 1.0          # 1.0 for futures; option delta in (0, 1] if used later
    as_of: Optional[date] = None

    @property
    def effective_lots(self) -> float:
        return self.lots * self.delta

    @property
    def notional_inr(self) -> float:
        return self.effective_lots * self.multiplier * self.mark_inr


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
    book_lots = sum(x.lots for x in b)
    book_notional = sum(x.notional_inr for x in b)
    hedge_lots = sum(x.effective_lots for x in h)
    hedge_notional = sum(x.notional_inr for x in h)
    return HedgeExposure(
        symbol=symbol,
        asset_class=asset_class,
        book_lots=book_lots,
        book_notional_inr=book_notional,
        hedge_lots=hedge_lots,
        hedge_notional_inr=hedge_notional,
        as_of=as_of,
        contract_notes=contract_notes,
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
    # notional per lot from book
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
    if abs(drift) * abs(
        exposure.book_notional_inr / exposure.book_lots if abs(exposure.book_lots) > 1e-12 else 0.0
    ) < band.min_notional_inr:
        # optional ₹ filter when configured
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
) -> str:
    """Careful wording: review / question only — never an order instruction."""
    h_txt = f"{h_actual:.0%}" if h_actual is not None else "n/a"
    direction = "increase" if drift_actionable > 0 else "reduce" if drift_actionable < 0 else "hold"
    return (
        f"HEDGE REVIEW — not an order. {symbol}: book {exposure.book_lots:+.2f} lots, "
        f"hedge {exposure.hedge_lots:+.2f} lots, ratio {h_txt} vs target {h_star:.0%} "
        f"({regime.value}). Model drift {drift_actionable:+.2f} lots ({direction}); "
        f"residual after step {residual:+.2f} lots. "
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

    suppress: Optional[str] = None
    if not force:
        if (
            days_to_roll is not None
            and 0 <= days_to_roll <= policy.roll_blackout_days
            and not breached
        ):
            suppress = "roll_blackout"
        if (
            days_since_last_prompt is not None
            and days_since_last_prompt < policy.min_days_between_prompts
            and not force
        ):
            suppress = suppress or "cooldown"

    urgency = "none"
    if breached and suppress is None:
        urgency = "elevated" if regime == RegimeLabel.STRESS else "review"

    h_act = exposure.hedge_ratio
    reason_parts = [
        f"h_star={h_star:.2f}",
        f"drift_lots={drift:.3f}",
        f"breached={breached}",
        f"regime={regime.value}",
    ]
    copy = build_review_copy(
        exposure.symbol, exposure, h_star, h_act, actionable, residual, regime
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

## Integration notes (v2 only)

| Concern | Approach |
|---------|----------|
| MCX roll | `contract_label` + `contract_notes` on legs; `days_to_roll` into `evaluate_symbol` |
| UI | Show `copy_review` only if `suppress_reason is None` and `urgency != "none"` |
| Ack | Treat each non-suppressed `HedgeReview` as portfolio-relevant signal |
| Journal | On ack, optional intended-trade: symbol, `drift_lots_actionable`, reason, regime |
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

---

## Non-goals

- Broker APIs, OMS, auto-send  
- Intraday continuous rebalancing without human ack  
- Full multi-asset mean-variance optimiser (optional later research)

---

Drafted: 2026-08-13  
Repo: `sanjaymaverick-cmd/portfolio`
