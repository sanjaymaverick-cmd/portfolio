from __future__ import annotations

from decimal import Decimal

from meridian.recommendations.shap_explain import ShapResult
from meridian.scoring.composite import FACTORS
from meridian.storage.schema import FactorScore

_LABEL = {
    "quality": "quality",
    "valuation": "valuation",
    "technical": "momentum",
    "ownership": "ownership",
    "sentiment": "sentiment",
}


def write_reasoning(
    *,
    symbol: str,
    action: str,
    composite: Decimal | None,
    confidence: Decimal | None,
    regime: str | None,
    row: FactorScore,
    shap: ShapResult,
    weight: Decimal | None,
    top_symbol: str | None,
    names: int,
) -> tuple[str, str]:
    bits: list[str] = []
    score_txt = f"{float(composite):.1f}" if composite is not None else "—"
    conf_txt = f"{float(confidence) * 100:.0f}%" if confidence is not None else "—"
    desk = f" in a {regime} regime" if regime else ""
    bits.append(
        f"{symbol} is a {action} at score {score_txt}{desk} (how sure: {conf_txt}). This is not an order."
    )
    pos = shap.positives[:2]
    neg = shap.negatives[:2]
    if pos:
        bits.append(
            "What is helping: "
            + "; ".join(
                f"{_LABEL[name]} {float(getattr(row, name)):.1f} ({value:+.2f} on the score)"
                for name, value in pos
                if getattr(row, name, None) is not None
            )
            + "."
        )
    if neg:
        bits.append(
            "What is holding it back: "
            + "; ".join(
                f"{_LABEL[name]} {float(getattr(row, name)):.1f} ({value:+.2f})"
                for name, value in neg
                if getattr(row, name, None) is not None
            )
            + "."
        )
    if not pos and not neg:
        present = [
            f"{_LABEL[name]} {float(getattr(row, name)):.1f}"
            for name in FACTORS
            if getattr(row, name, None) is not None
        ]
        if present:
            bits.append("Factor marks: " + ", ".join(present) + ".")
    note = portfolio_note(symbol, weight, top_symbol, names)
    return " ".join(bits), note


def portfolio_note(
    symbol: str, weight: Decimal | None, top_symbol: str | None, names: int
) -> str:
    if weight is None:
        return f"{names} names on the book."
    pct = float(weight)
    if pct >= 12:
        return f"{symbol} is a large slice ({pct:.1f}%) of the book — adding more would make it even bigger."
    if pct >= 8:
        return f"{symbol} is {pct:.1f}% of this {names}-name book."
    if top_symbol == symbol:
        return f"This is the biggest name, at {pct:.1f}% of the book."
    return f"{pct:.1f}% of a {names}-name book."
