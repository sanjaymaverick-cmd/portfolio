from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from meridian.scoring.composite import FACTORS, composite_score
from meridian.storage.schema import FactorScore

BASELINE = 5.0
_CACHE: dict[str, object] = {}


@dataclass
class ShapResult:
    base: float
    phis: dict[str, float]
    prediction: float
    engine: str

    @property
    def positives(self) -> list[tuple[str, float]]:
        return sorted(
            ((name, value) for name, value in self.phis.items() if value > 0.02),
            key=lambda item: item[1],
            reverse=True,
        )

    @property
    def negatives(self) -> list[tuple[str, float]]:
        return sorted(
            ((name, value) for name, value in self.phis.items() if value < -0.02),
            key=lambda item: item[1],
        )


def linear_shap(row: FactorScore, weights: dict[str, Decimal]) -> ShapResult:
    present: list[str] = []
    values: dict[str, float] = {}
    mass = 0.0
    for name in FACTORS:
        raw = getattr(row, name, None)
        weight = float(weights.get(name, 0) or 0)
        if raw is None or weight <= 0:
            continue
        present.append(name)
        values[name] = float(raw)
        mass += weight
    if mass <= 0:
        return ShapResult(base=BASELINE, phis={}, prediction=BASELINE, engine="linear")
    base = BASELINE
    phis = {name: (float(weights[name]) / mass) * (values[name] - BASELINE) for name in present}
    pred = base + sum(phis.values())
    return ShapResult(base=base, phis=phis, prediction=pred, engine="linear")


def explain(row: FactorScore, weights: dict[str, Decimal]) -> ShapResult:
    exact = linear_shap(row, weights)
    tree = _tree_shap(row, weights)
    if tree is None:
        return exact
    recon = tree.base + sum(tree.phis.values())
    if abs(recon - exact.prediction) > 0.75:
        return exact
    return tree


def _tree_shap(row: FactorScore, weights: dict[str, Decimal]) -> ShapResult | None:
    try:
        import numpy as np
        import shap
        from xgboost import XGBRegressor
    except ImportError:
        return None
    key = _weight_key(weights)
    bundle = _CACHE.get(key)
    if bundle is None:
        model = _fit_surrogate(weights, np, XGBRegressor)
        if model is None:
            return None
        explainer = shap.TreeExplainer(model)
        _CACHE[key] = (model, explainer)
    else:
        model, explainer = bundle  # type: ignore[misc]
    vector = _vector(row)
    sample = __import__("numpy").array([vector], dtype=float)
    try:
        values = explainer.shap_values(sample)
        base = explainer.expected_value
    except Exception:  # noqa: BLE001
        return None
    if hasattr(base, "__len__"):
        base = float(base[0])
    else:
        base = float(base)
    flat = values[0] if getattr(values, "ndim", 1) > 1 else values
    phis = {name: float(flat[index]) for index, name in enumerate(FACTORS)}
    pred = float(model.predict(sample)[0])
    return ShapResult(base=base, phis=phis, prediction=pred, engine="shap_xgb")


def _fit_surrogate(weights: dict[str, Decimal], np, xgb_cls):  # noqa: ANN001
    rng = np.random.default_rng(7)
    n = 900
    X = rng.uniform(0.5, 9.5, size=(n, len(FACTORS)))
    y = []
    for row in X:
        fake = FactorScore(symbol="SYN")
        for name, value in zip(FACTORS, row, strict=False):
            setattr(fake, name, Decimal(str(round(float(value), 4))))
        score = composite_score(fake, weights)
        y.append(float(score) if score is not None else BASELINE)
    model = xgb_cls(
        n_estimators=48,
        max_depth=3,
        learning_rate=0.12,
        subsample=0.9,
        colsample_bytree=1.0,
        objective="reg:squarederror",
        verbosity=0,
        n_jobs=1,
    )
    model.fit(X, np.array(y, dtype=float))
    return model


def _vector(row: FactorScore) -> list[float]:
    out: list[float] = []
    for name in FACTORS:
        raw = getattr(row, name, None)
        out.append(float(raw) if raw is not None else BASELINE)
    return out


def _weight_key(weights: dict[str, Decimal]) -> str:
    payload = ",".join(f"{name}:{float(weights.get(name, 0)):.4f}" for name in FACTORS)
    return hashlib.sha1(payload.encode()).hexdigest()
