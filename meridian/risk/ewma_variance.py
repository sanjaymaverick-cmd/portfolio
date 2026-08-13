from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class EwmaVariance:
    """Nifty-only variance filter. Separate from pairwise beta Ewma in risk.math."""

    lam: float = 0.94
    var: float = 0.0
    n_obs: int = 0

    def update(self, ret: float) -> float:
        if self.n_obs == 0:
            self.var = ret * ret
        else:
            self.var = self.lam * self.var + (1.0 - self.lam) * ret * ret
        self.n_obs += 1
        return self.var

    def update_series(self, returns: list[float]) -> list[float]:
        path: list[float] = []
        for ret in returns:
            path.append(self.update(ret))
        return path

    @property
    def vol(self) -> float:
        return math.sqrt(max(self.var, 0.0))

    @property
    def vol_ann(self) -> float:
        return self.vol * math.sqrt(252.0)

    def to_dict(self) -> dict[str, float | int]:
        return {"lam": self.lam, "var": self.var, "n_obs": self.n_obs}

    @classmethod
    def from_dict(cls, payload: dict[str, float | int]) -> EwmaVariance:
        return cls(
            lam=float(payload.get("lam", 0.94)),
            var=float(payload.get("var", 0.0)),
            n_obs=int(payload.get("n_obs", 0)),
        )
