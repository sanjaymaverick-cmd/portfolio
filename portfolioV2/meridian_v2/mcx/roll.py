from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ContractSpec:
    symbol_key: str
    near_label: str
    next_label: str
    roll_date: date | None
    multiplier: float = 1.0
    series_kind: str = "CONTINUOUS"
    notes: str = ""


@dataclass(frozen=True)
class ContinuousMark:
    symbol_key: str
    series_kind: str
    contract_label: str
    mark: float | None
    quality: str
    days_to_roll: int | None
    note: str


def days_to_roll(as_of: date, roll_date: date | None) -> int | None:
    if roll_date is None:
        return None
    return (roll_date - as_of).days


def ui_series_label(spec: ContractSpec, *, prefer_continuous: bool = True) -> str:
    """Never present a rolled contract as a bare equity-like ticker."""
    if prefer_continuous or spec.series_kind == "CONTINUOUS":
        near = spec.near_label or "NEAR"
        return f"{spec.symbol_key} · CONTINUOUS (near {near})"
    label = spec.near_label or spec.symbol_key
    return f"{spec.symbol_key} · CONTRACT {label}"


def evaluate_continuous(
    spec: ContractSpec,
    *,
    near_mark: float | None,
    next_mark: float | None,
    as_of: date,
    blackout_days: int = 3,
) -> ContinuousMark:
    dtr = days_to_roll(as_of, spec.roll_date)
    in_roll = dtr is not None and 0 <= dtr <= blackout_days
    if near_mark is None and next_mark is None:
        return ContinuousMark(
            symbol_key=spec.symbol_key,
            series_kind="CONTINUOUS",
            contract_label="CONTINUOUS",
            mark=None,
            quality="missing",
            days_to_roll=dtr,
            note="No free MCX mark available — data-quality flag: missing.",
        )
    if in_roll and next_mark is not None and near_mark is not None:
        # Do not silently jump: blend is explicit metadata, not a hidden stitch.
        mark = near_mark
        return ContinuousMark(
            symbol_key=spec.symbol_key,
            series_kind="CONTINUOUS",
            contract_label="CONTINUOUS",
            mark=mark,
            quality="roll_window",
            days_to_roll=dtr,
            note=(
                f"Roll window: near {spec.near_label} {near_mark:.2f} vs "
                f"next {spec.next_label} {next_mark:.2f}. Continuous series is still "
                f"labelled CONTINUOUS — not a single equity-like ticker."
            ),
        )
    mark = near_mark if near_mark is not None else next_mark
    quality = "ok" if near_mark is not None else "degraded"
    return ContinuousMark(
        symbol_key=spec.symbol_key,
        series_kind="CONTINUOUS",
        contract_label="CONTINUOUS",
        mark=mark,
        quality=quality,
        days_to_roll=dtr,
        note=ui_series_label(spec),
    )
