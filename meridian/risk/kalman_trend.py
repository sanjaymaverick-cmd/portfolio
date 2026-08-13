from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class KalmanTrend:
    """Local linear trend on log price. State is [level, trend]."""

    q_level: float = 1.0e-5
    q_trend: float = 1.0e-7
    r: float = 1.0e-4
    level: float | None = None
    trend: float = 0.0
    p00: float = 1.0
    p01: float = 0.0
    p10: float = 0.0
    p11: float = 1.0
    trends: list[float] = field(default_factory=list)

    def update(self, price: float) -> float:
        if price <= 0:
            return self.trend
        z = math.log(price)
        if self.level is None:
            self.level = z
            self.trend = 0.0
            self.trends.append(0.0)
            return 0.0
        level_p = self.level + self.trend
        trend_p = self.trend
        p00 = self.p00 + self.p01 + self.p10 + self.p11 + self.q_level
        p01 = self.p01 + self.p11
        p10 = self.p10 + self.p11
        p11 = self.p11 + self.q_trend
        innov = z - level_p
        scale = p00 + self.r
        k0 = p00 / scale
        k1 = p10 / scale
        self.level = level_p + k0 * innov
        self.trend = trend_p + k1 * innov
        self.p00 = (1.0 - k0) * p00
        self.p01 = (1.0 - k0) * p01
        self.p10 = -k1 * p00 + p10
        self.p11 = -k1 * p01 + p11
        self.trends.append(self.trend)
        if len(self.trends) > 120:
            self.trends = self.trends[-120:]
        return self.trend

    def update_series(self, closes: list[float]) -> list[float]:
        path: list[float] = []
        for price in closes:
            path.append(self.update(price))
        return path

    @property
    def trend_ann_pct(self) -> float:
        return self.trend * 252.0 * 100.0

    def trend_z(self, window: int = 60) -> float | None:
        hist = self.trends[-window:]
        if len(hist) < 10:
            return None
        mean = sum(hist) / len(hist)
        var = sum((item - mean) ** 2 for item in hist) / (len(hist) - 1)
        if var <= 1e-18:
            return 0.0
        return (self.trend - mean) / math.sqrt(var)

    def to_dict(self) -> dict[str, float | list[float] | None]:
        return {
            "q_level": self.q_level,
            "q_trend": self.q_trend,
            "r": self.r,
            "level": self.level,
            "trend": self.trend,
            "p00": self.p00,
            "p01": self.p01,
            "p10": self.p10,
            "p11": self.p11,
            "trends": list(self.trends[-80:]),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> KalmanTrend:  # noqa: ANN401
        return cls(
            q_level=float(payload.get("q_level", 1.0e-5)),
            q_trend=float(payload.get("q_trend", 1.0e-7)),
            r=float(payload.get("r", 1.0e-4)),
            level=payload.get("level"),
            trend=float(payload.get("trend", 0.0)),
            p00=float(payload.get("p00", 1.0)),
            p01=float(payload.get("p01", 0.0)),
            p10=float(payload.get("p10", 0.0)),
            p11=float(payload.get("p11", 1.0)),
            trends=[float(item) for item in payload.get("trends") or []],
        )
