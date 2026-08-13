from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from meridian.config import Settings, get_settings
from meridian.recommendations.copy import write_reasoning
from meridian.recommendations.shap_explain import explain
from meridian.scoring.composite import blend_weights
from meridian.storage.attributions import AttributionRepo
from meridian.storage.fundamentals import FactorRepo
from meridian.storage.regime import RegimeRepo
from meridian.storage.repositories import HoldingRepo


class ExplainService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.factors = FactorRepo(session)
        self.regimes = RegimeRepo(session)
        self.holdings = HoldingRepo(session)
        self.attributions = AttributionRepo(session)

    def explain_all(self, symbol: str | None = None) -> int:
        regime = self.regimes.latest()
        weights = blend_weights(regime, self.settings.scoring)
        book = self.holdings.summary()
        lots = self.holdings.list()
        mass = float(book.market_value or 0) or 1.0
        weight_map: dict[str, Decimal] = {}
        for lot in lots:
            value = float(lot.quantity * (lot.last_price or lot.avg_cost))
            key = lot.symbol.upper()
            weight_map[key] = weight_map.get(key, Decimal("0")) + Decimal(str(100.0 * value / mass))
        if symbol:
            rows = [self.factors.get(symbol)]
        else:
            from sqlalchemy import select
            from meridian.storage.schema import FactorScore

            rows = list(self.session.scalars(select(FactorScore)))
        written = 0
        for row in rows:
            if row is None or row.composite is None:
                continue
            shap = explain(row, weights)
            reasoning, note = write_reasoning(
                symbol=row.symbol,
                action=row.action or "—",
                composite=row.composite,
                confidence=row.confidence,
                regime=regime.label if regime else None,
                row=row,
                shap=shap,
                weight=weight_map.get(row.symbol),
                top_symbol=book.top_symbol,
                names=book.names,
            )
            self.attributions.record(
                symbol=row.symbol,
                regime=regime.label if regime else None,
                action=row.action,
                composite=row.composite,
                base_value=shap.base,
                engine=shap.engine,
                phis=shap.phis,
                reasoning=reasoning,
                portfolio_note=note,
            )
            written += 1
        return written
