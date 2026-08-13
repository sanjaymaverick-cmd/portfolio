"""Paper backtest *report hooks* — no execution."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from meridian_v2.signals.engines import evaluate_signals
from meridian_v2.storage.schema import BacktestRun, PriceCache


def synthetic_path(price: PriceCache, steps: int = 12) -> list[dict]:
    last = price.last or 100.0
    prev = price.prev_close or last
    step = (last - prev) / max(steps, 1)
    bars = []
    px = prev
    for i in range(steps):
        px = px + step
        bars.append(
            {
                "last": px,
                "sma": prev,
                "sma50": prev,
                "high20": max(prev, last),
                "low20": min(prev, last) * 0.98,
                "volume": (price.volume or 1000) * (1.0 + 0.05 * i),
                "prev_volume": price.prev_volume or 1000,
            }
        )
    return bars


def run_paper_backtest(
    session: Session,
    price: PriceCache,
    *,
    regime: str = "Elevated",
    asset_class: str = "equity",
    score: float | None = 5.0,
) -> BacktestRun:
    bars = synthetic_path(price)
    hits = 0
    lines = [f"PAPER BACKTEST {price.symbol} · {len(bars)} bars · regime {regime} · not an order"]
    for i, bar in enumerate(bars, start=1):
        raws = evaluate_signals(
            symbol=price.symbol,
            asset_class=asset_class,
            score=score,
            last=bar["last"],
            sma=bar["sma"],
            sma50=bar["sma50"],
            weekly_last=price.weekly_last,
            weekly_sma=price.weekly_sma,
            high20=bar["high20"],
            low20=bar["low20"],
            volume=bar["volume"],
            prev_volume=bar["prev_volume"],
            regime=regime,
            in_book=True,
            usdinr_move_pct=None,
            commodity_stress=False,
        )
        if raws:
            hits += 1
            names = ", ".join(sorted({r.rule_name for r in raws}))
            lines.append(f"  bar {i}: last {bar['last']:.2f} → {names}")
    report = "\n".join(lines) + f"\nHits {hits}/{len(bars)}"
    row = BacktestRun(
        symbol=price.symbol,
        rule_name="all_families",
        bars=len(bars),
        hits=hits,
        report=report,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(row)
    session.flush()
    return row
