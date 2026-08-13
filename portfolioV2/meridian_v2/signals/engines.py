from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawSignal:
    rule_name: str
    symbol: str
    strength: float
    reason: str
    portfolio_relevant: bool
    params: str = ""
    suggestion: str = "Hold"


def score_threshold_regime(
    symbol: str,
    score: float | None,
    regime: str,
    *,
    threshold: float = 4.0,
) -> RawSignal | None:
    if score is None:
        return None
    if score <= threshold and regime != "Calm":
        return RawSignal(
            rule_name="score_threshold_regime",
            symbol=symbol,
            strength=max(0.0, (threshold - score) / 10.0),
            reason=(
                f"Multi-factor score {score:.1f} is at/under {threshold:.0f} while regime is {regime}. "
                f"Review whether this name still belongs on the active desk."
            ),
            portfolio_relevant=True,
            params=f"threshold={threshold}",
            suggestion="Hold",
        )
    return None


def trend_ma_regime(
    symbol: str,
    last: float | None,
    sma: float | None,
    regime: str,
    *,
    weekly_last: float | None = None,
    weekly_sma: float | None = None,
) -> RawSignal | None:
    if last is None or sma is None or sma == 0:
        return None
    daily_below = last < sma
    weekly_aligned = True
    if weekly_last is not None and weekly_sma:
        weekly_aligned = weekly_last < weekly_sma
    if daily_below and weekly_aligned and regime in {"Elevated", "Stress"}:
        gap = (sma - last) / sma
        return RawSignal(
            rule_name="trend_ma_regime",
            symbol=symbol,
            strength=min(1.0, gap * 8),
            reason=(
                f"Last {last:.2f} is below SMA {sma:.2f} under {regime}"
                f"{' with weekly confirmation' if weekly_last is not None else ''}. "
                f"Consider waiting for daily + weekly alignment before adding risk."
            ),
            portfolio_relevant=True,
            params="sma_window=20;weekly=1",
            suggestion="Hold",
        )
    return None


def mean_reversion_bands(
    symbol: str,
    last: float | None,
    mid: float | None,
    high20: float | None,
    low20: float | None,
    regime: str,
) -> RawSignal | None:
    if last is None or low20 is None or high20 is None or high20 <= low20:
        return None
    band = high20 - low20
    if last <= low20 + 0.1 * band and regime != "Stress":
        return RawSignal(
            rule_name="mean_reversion_bands",
            symbol=symbol,
            strength=min(1.0, (low20 + 0.1 * band - last) / band),
            reason=(
                f"Last {last:.2f} is near the 20-session low {low20:.2f} (mid {mid or 0:.2f}) "
                f"under {regime}. Review a mean-reversion *consider*, not an order."
            ),
            portfolio_relevant=True,
            params="lookback=20;band=0.1",
            suggestion="Hold",
        )
    if last >= high20 - 0.1 * band:
        return RawSignal(
            rule_name="mean_reversion_bands",
            symbol=symbol,
            strength=min(1.0, (last - (high20 - 0.1 * band)) / band),
            reason=(
                f"Last {last:.2f} is near the 20-session high {high20:.2f} under {regime}. "
                f"Consider waiting rather than chasing."
            ),
            portfolio_relevant=True,
            params="lookback=20;band=0.1",
            suggestion="Hold",
        )
    return None


def breakout_volume(
    symbol: str,
    last: float | None,
    high20: float | None,
    volume: float | None,
    prev_volume: float | None,
    regime: str,
) -> RawSignal | None:
    if last is None or high20 is None:
        return None
    vol_ok = volume is not None and prev_volume not in (None, 0) and volume >= 1.4 * prev_volume
    if last > high20 and vol_ok and regime != "Stress":
        return RawSignal(
            rule_name="breakout_volume",
            symbol=symbol,
            strength=min(1.0, (last / high20 - 1.0) * 8),
            reason=(
                f"Breakout: last {last:.2f} above 20-session high {high20:.2f} with volume confirmation "
                f"({volume:.0f} vs {prev_volume:.0f}) under {regime}. Review, do not chase automatically."
            ),
            portfolio_relevant=True,
            params="high20;vol_ratio=1.4",
            suggestion="Hold",
        )
    if last > high20 and not vol_ok:
        return RawSignal(
            rule_name="breakout_volume",
            symbol=symbol,
            strength=0.2,
            reason=(
                f"Price {last:.2f} printed above {high20:.2f} but volume is not confirming. "
                f"Note only — wait for participation."
            ),
            portfolio_relevant=False,
            params="high20;vol_ratio=1.4",
            suggestion="Hold",
        )
    return None


def cross_asset_overlay(
    symbol: str,
    asset_class: str,
    regime: str,
    *,
    usdinr_move_pct: float | None,
    commodity_stress: bool,
) -> RawSignal | None:
    if asset_class != "equity":
        return None
    if (usdinr_move_pct is not None and usdinr_move_pct >= 1.0) or commodity_stress or regime == "Stress":
        why = []
        if usdinr_move_pct is not None and usdinr_move_pct >= 1.0:
            why.append(f"USDINR {usdinr_move_pct:+.2f}%")
        if commodity_stress:
            why.append("commodity tape in stress")
        why.append(f"regime {regime}")
        return RawSignal(
            rule_name="cross_asset_overlay",
            symbol=symbol,
            strength=0.55,
            reason=(
                "Equity add is tempered by " + "; ".join(why) + ". "
                "Consider waiting until the macro overlay cools."
            ),
            portfolio_relevant=True,
            params="usdinr_gate=1.0;commodity_stress=1",
            suggestion="Hold",
        )
    return None


def evaluate_signals(
    *,
    symbol: str,
    asset_class: str,
    score: float | None,
    last: float | None,
    sma: float | None,
    sma50: float | None,
    weekly_last: float | None,
    weekly_sma: float | None,
    high20: float | None,
    low20: float | None,
    volume: float | None,
    prev_volume: float | None,
    regime: str,
    in_book: bool,
    usdinr_move_pct: float | None,
    commodity_stress: bool,
) -> list[RawSignal]:
    raws = [
        score_threshold_regime(symbol, score, regime),
        trend_ma_regime(symbol, last, sma, regime, weekly_last=weekly_last, weekly_sma=weekly_sma),
        mean_reversion_bands(symbol, last, sma, high20, low20, regime),
        breakout_volume(symbol, last, high20, volume, prev_volume, regime),
        cross_asset_overlay(
            symbol,
            asset_class,
            regime,
            usdinr_move_pct=usdinr_move_pct,
            commodity_stress=commodity_stress,
        ),
    ]
    out: list[RawSignal] = []
    for raw in raws:
        if raw is None:
            continue
        out.append(
            RawSignal(
                **{
                    **raw.__dict__,
                    "portfolio_relevant": raw.portfolio_relevant and in_book,
                }
            )
        )
    return out
