"""Binding UI copy rules: review / consider / note — never execute language."""

from __future__ import annotations

FORBIDDEN = (
    "you should hedge",
    "execute",
    "must reduce",
    "buy usd",
    "must hedge",
    "place order",
    "auto-send",
)


def assert_review_copy(text: str) -> str:
    lowered = text.lower()
    for phrase in FORBIDDEN:
        if phrase in lowered:
            raise ValueError(f"forbidden execution language: {phrase!r}")
    return text


def fx_review_copy(*, pair: str, move_pct: float, regime: str, why: str) -> str:
    direction = "up" if move_pct >= 0 else "down"
    text = (
        f"FX REVIEW — not an order. {pair} is {direction} {abs(move_pct):.2f}% "
        f"({regime}). {why} Review whether the current hedge still matches the book, "
        f"or note the residual and wait?"
    )
    return assert_review_copy(text)
