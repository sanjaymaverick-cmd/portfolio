from __future__ import annotations

from decimal import Decimal

from meridian.data_providers.screener import FundamentalSnap
from meridian.scoring.bands import EV, PB, PE, interpolate, typical_for
from meridian.scoring.quality import _weighted

WEIGHTS = {
    "pe": Decimal("0.40"),
    "pb": Decimal("0.25"),
    "ev_ebitda": Decimal("0.20"),
    "vs_sector": Decimal("0.15"),
}


def score_valuation(snap: FundamentalSnap) -> tuple[Decimal | None, dict[str, Decimal | None]]:
    typical = typical_for(snap.sector, snap.industry)
    parts: dict[str, Decimal | None] = {
        "pe": interpolate(snap.pe, PE),
        "pb": interpolate(snap.pb, PB),
        "ev_ebitda": interpolate(snap.ev_ebitda, EV),
        "vs_sector": _vs_sector(snap, typical),
    }
    return _weighted(parts, WEIGHTS), parts


def _vs_sector(snap: FundamentalSnap, typical: dict[str, float]) -> Decimal | None:
    premia: list[Decimal] = []
    for field, key in (("pe", "pe"), ("pb", "pb"), ("ev_ebitda", "ev")):
        value = getattr(snap, field)
        bench = typical.get(key)
        if value is None or not bench:
            continue
        premia.append((value / Decimal(str(bench))) - Decimal("1"))
    if not premia:
        return None
    avg = sum(premia, Decimal("0")) / Decimal(len(premia))
    # -30% vs typical → ~8.8; par → 5.2; +50% → ~2.4
    return interpolate(avg * Decimal("100"), [(-40, 9.4), (-15, 7.6), (0, 5.2), (25, 3.4), (60, 1.8)])
