"""Regime-conditioned SHAP and written recommendations."""

from meridian.recommendations.service import ExplainService
from meridian.recommendations.shap_explain import ShapResult, explain, linear_shap

__all__ = ["ExplainService", "ShapResult", "explain", "linear_shap"]
