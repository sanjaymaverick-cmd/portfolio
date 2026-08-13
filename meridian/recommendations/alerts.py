from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class AlertHit:
    kind: str
    symbol: str
    severity: str
    title: str
    detail: str
    metric: float | None = None


def weight_hit(symbol: str, weight_pct: float, *, threshold: float, high: float) -> AlertHit | None:
    if weight_pct < threshold:
        return None
    severity = "high" if weight_pct >= high else "watch"
    return AlertHit(
        kind="weight",
        symbol=symbol,
        severity=severity,
        title=f"{symbol} is {weight_pct:.1f}% of book",
        detail=f"Single-name weight {weight_pct:.1f}% versus a {threshold:.0f}% monitor.",
        metric=weight_pct,
    )


def pledge_hit(
    symbol: str,
    pledge: float | None,
    previous: float | None,
    *,
    step: float,
    abs_limit: float,
) -> AlertHit | None:
    if pledge is None:
        return None
    if previous is not None and pledge - previous >= step:
        return AlertHit(
            kind="pledge",
            symbol=symbol,
            severity="high" if pledge >= abs_limit else "watch",
            title=f"{symbol} promoter pledge +{pledge - previous:.1f} pp",
            detail=f"Pledge moved from {previous:.1f}% to {pledge:.1f}%.",
            metric=pledge,
        )
    if pledge >= abs_limit:
        return AlertHit(
            kind="pledge",
            symbol=symbol,
            severity="high" if pledge >= abs_limit * 1.5 else "watch",
            title=f"{symbol} promoter pledge {pledge:.1f}%",
            detail=f"Pledge is at {pledge:.1f}% (desk limit {abs_limit:.0f}%).",
            metric=pledge,
        )
    return None


def volume_hit(symbol: str, volume_ratio: float | None, *, threshold: float) -> AlertHit | None:
    if volume_ratio is None or volume_ratio >= threshold:
        return None
    return AlertHit(
        kind="volume",
        symbol=symbol,
        severity="watch",
        title=f"{symbol} volume {volume_ratio:.2f}× recent average",
        detail="Trading volume is much lower than usual. Delivery figures are not available here.",
        metric=volume_ratio,
    )


def results_hit(
    symbol: str,
    titles: list[str],
    as_of: datetime,
    published: datetime | None,
    *,
    lookback_days: int,
) -> AlertHit | None:
    if not titles:
        return None
    when = published or as_of
    if (as_of.date() - when.date()) > timedelta(days=lookback_days):
        return None
    lead = titles[0]
    return AlertHit(
        kind="results",
        symbol=symbol,
        severity="info",
        title=f"{symbol} results in today's news",
        detail=lead,
        metric=float(len(titles)),
    )


def action_hit(symbol: str, current: str | None, previous: str | None) -> AlertHit | None:
    if not current or not previous or current == previous:
        return None
    return AlertHit(
        kind="action",
        symbol=symbol,
        severity="watch",
        title=f"{symbol} {previous} → {current}",
        detail=f"Recommendation changed from {previous} to {current}.",
    )


def regime_hit(current: str | None, previous: str | None) -> AlertHit | None:
    if not current or not previous or current == previous:
        return None
    severity = "high" if current == "Stress" or previous == "Stress" else "watch"
    return AlertHit(
        kind="regime",
        symbol="MARKET",
        severity=severity,
        title=f"Regime {previous} → {current}",
        detail=f"Hysteresis label moved from {previous} to {current}.",
    )
