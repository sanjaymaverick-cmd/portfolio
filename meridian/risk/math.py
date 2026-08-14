from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from meridian.storage.schema import PriceBar


@dataclass(frozen=True, slots=True)
class AlignedSeries:
    dates: list[datetime]
    asset: list[float]
    market: list[float]
    asset_px: list[float]
    market_px: list[float]
    volume: list[float]


def align_closes(asset: list[PriceBar], market: list[PriceBar]) -> AlignedSeries | None:
    by_day = {
        _day(bar.bar_date): (float(bar.close), float(bar.volume or 0))
        for bar in asset
        if bar.close
    }
    mkt = {_day(bar.bar_date): float(bar.close) for bar in market if bar.close}
    dates = sorted(set(by_day) & set(mkt))
    if len(dates) < 5:
        return None
    asset_px = [by_day[d][0] for d in dates]
    volume = [by_day[d][1] for d in dates]
    market_px = [mkt[d] for d in dates]
    return AlignedSeries(
        dates=dates,
        asset=_returns(asset_px),
        market=_returns(market_px),
        asset_px=asset_px,
        market_px=market_px,
        volume=volume,
    )


def sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for index in range(1, period + 1):
        delta = closes[index] - closes[index - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    for index in range(period + 1, len(closes)):
        delta = closes[index] - closes[index - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def rolling_corr_beta(
    asset: list[float], market: list[float], window: int
) -> tuple[list[float | None], list[float | None]]:
    n = min(len(asset), len(market))
    rhos: list[float | None] = [None] * n
    betas: list[float | None] = [None] * n
    for end in range(window, n + 1):
        ys = asset[end - window : end]
        xs = market[end - window : end]
        rho, beta = corr_beta(ys, xs)
        rhos[end - 1] = rho
        betas[end - 1] = beta
    return rhos, betas


def corr_beta(ys: list[float], xs: list[float]) -> tuple[float | None, float | None]:
    n = min(len(ys), len(xs))
    if n < 3:
        return None, None
    mean_x = sum(xs[:n]) / n
    mean_y = sum(ys[:n]) / n
    cov = 0.0
    var_x = 0.0
    var_y = 0.0
    for x, y in zip(xs[:n], ys[:n], strict=False):
        dx = x - mean_x
        dy = y - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy
    if var_x <= 0 or var_y <= 0:
        return None, None
    cov /= n - 1
    var_x /= n - 1
    var_y /= n - 1
    return cov / math.sqrt(var_x * var_y), cov / var_x


@dataclass
class Ewma:
    var_m: float
    var_i: float
    cov: float
    lam: float = 0.94

    def update(self, r_i: float, r_m: float) -> None:
        k = 1.0 - self.lam
        self.var_m = self.lam * self.var_m + k * r_m * r_m
        self.var_i = self.lam * self.var_i + k * r_i * r_i
        self.cov = self.lam * self.cov + k * r_i * r_m

    @property
    def beta(self) -> float | None:
        if self.var_m <= 1e-16:
            return None
        return self.cov / self.var_m

    @property
    def rho(self) -> float | None:
        denom = math.sqrt(self.var_i * self.var_m)
        if denom <= 1e-16:
            return None
        return max(-1.0, min(1.0, self.cov / denom))


def seed_ewma(asset: list[float], market: list[float], lam: float, warmup: int = 20) -> Ewma:
    n = min(len(asset), len(market))
    take = min(max(warmup, 10), n)
    _, beta = corr_beta(asset[:take], market[:take])
    var_m = _var(market[:take]) or 1e-8
    var_i = _var(asset[:take]) or 1e-8
    # Fall back to beta=1.0 only when corr_beta could not compute one (None);
    # a genuine beta of 0.0 (uncorrelated over the warmup) must be preserved.
    cov = (1.0 if beta is None else beta) * var_m
    state = Ewma(var_m=var_m, var_i=var_i, cov=cov, lam=lam)
    for r_i, r_m in zip(asset[take:], market[take:], strict=False):
        state.update(r_i, r_m)
    return state


def ewma_path(asset: list[float], market: list[float], lam: float, warmup: int = 20) -> list[float | None]:
    n = min(len(asset), len(market))
    out: list[float | None] = [None] * n
    if n < warmup:
        return out
    state = Ewma(var_m=1e-8, var_i=1e-8, cov=1e-8, lam=lam)
    # seed on first warmup points without recording
    for index in range(warmup):
        state.update(asset[index], market[index])
        out[index] = state.beta
    for index in range(warmup, n):
        state.update(asset[index], market[index])
        out[index] = state.beta
    return out


def shrink_beta(beta: float | None, shrinkage: float) -> float | None:
    if beta is None:
        return None
    s = max(0.0, min(1.0, shrinkage))
    return (1.0 - s) * beta + s * 1.0


def relative_strength(asset_px: list[float], market_px: list[float], window: int = 60) -> float | None:
    if len(asset_px) < window + 1 or len(market_px) < window + 1:
        window = min(len(asset_px), len(market_px)) - 1
    if window < 5:
        return None
    a0, a1 = asset_px[-window - 1], asset_px[-1]
    m0, m1 = market_px[-window - 1], market_px[-1]
    if a0 <= 0 or m0 <= 0:
        return None
    return ((a1 / a0) - 1.0) - ((m1 / m0) - 1.0)


def volume_ratio(volume: list[float], short: int = 5, long: int = 20) -> float | None:
    if len(volume) < long:
        return None
    short_avg = sum(volume[-short:]) / short
    long_avg = sum(volume[-long:]) / long
    if long_avg <= 0:
        return None
    return short_avg / long_avg


def _returns(prices: list[float]) -> list[float]:
    out: list[float] = []
    for index in range(1, len(prices)):
        prev = prices[index - 1]
        out.append((prices[index] / prev) - 1.0 if prev else 0.0)
    return out


def _var(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mean = sum(xs) / len(xs)
    return sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)


def _day(value: datetime) -> datetime:
    if hasattr(value, "date"):
        return datetime.combine(value.date(), datetime.min.time())
    return value
