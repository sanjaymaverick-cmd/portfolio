from __future__ import annotations

from decimal import Decimal

from meridian.domain.money import format_inr, format_pct, format_qty


def signed_class(value: Decimal | float | int | None) -> str:
    if value is None:
        return "num"
    number = float(value)
    if number > 0:
        return "num up"
    if number < 0:
        return "num down"
    return "num"


def weight_bar(pct: Decimal | float | None) -> str:
    if pct is None:
        return "0"
    return f"{max(0.0, min(100.0, float(pct))):.2f}"


FILTERS = {
    "inr": lambda v: format_inr(v, compact=False),
    "inr_c": lambda v: format_inr(v, compact=True),
    "inr_s": lambda v: format_inr(v, compact=True, signed=True),
    "pct": lambda v: format_pct(v),
    "qty": format_qty,
    "sclass": signed_class,
    "wbar": weight_bar,
}
