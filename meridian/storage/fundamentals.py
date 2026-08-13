from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.data_providers.screener import FundamentalSnap
from meridian.storage.schema import FactorScore, Fundamental


class FundamentalRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, symbol: str) -> Fundamental | None:
        return self.session.get(Fundamental, symbol.upper())

    def upsert(self, snap: FundamentalSnap) -> Fundamental:
        row = self.get(snap.symbol)
        payload = {
            "source": snap.source,
            "screener_url": snap.screener_url,
            "company_name": snap.company_name,
            "sector": snap.sector,
            "industry": snap.industry,
            "market_cap_cr": snap.market_cap_cr,
            "current_price": snap.current_price,
            "pe": snap.pe,
            "book_value": snap.book_value,
            "pb": snap.pb,
            "dividend_yield": snap.dividend_yield,
            "roce": snap.roce,
            "roe": snap.roe,
            "roe_5y": snap.roe_5y,
            "opm": snap.opm,
            "opm_5y_mean": snap.opm_5y_mean,
            "opm_5y_std": snap.opm_5y_std,
            "debt_to_equity": snap.debt_to_equity,
            "cfo_to_op": snap.cfo_to_op,
            "ev_ebitda": snap.ev_ebitda,
            "sales_cagr_3y": snap.sales_cagr_3y,
            "sales_cagr_5y": snap.sales_cagr_5y,
            "profit_cagr_3y": snap.profit_cagr_3y,
            "profit_cagr_5y": snap.profit_cagr_5y,
            "fetched_at": datetime.now(),
            "as_of": snap.as_of,
            "notes": snap.notes,
        }
        if row:
            for key, value in payload.items():
                setattr(row, key, value)
        else:
            row = Fundamental(symbol=snap.symbol.upper(), **payload)
            self.session.add(row)
        self.session.flush()
        return row

    def to_snap(self, row: Fundamental) -> FundamentalSnap:
        return FundamentalSnap(
            symbol=row.symbol,
            source=row.source,
            screener_url=row.screener_url,
            company_name=row.company_name,
            sector=row.sector,
            industry=row.industry,
            market_cap_cr=row.market_cap_cr,
            current_price=row.current_price,
            pe=row.pe,
            book_value=row.book_value,
            pb=row.pb,
            dividend_yield=row.dividend_yield,
            roce=row.roce,
            roe=row.roe,
            roe_5y=row.roe_5y,
            opm=row.opm,
            opm_5y_mean=row.opm_5y_mean,
            opm_5y_std=row.opm_5y_std,
            debt_to_equity=row.debt_to_equity,
            cfo_to_op=row.cfo_to_op,
            ev_ebitda=row.ev_ebitda,
            sales_cagr_3y=row.sales_cagr_3y,
            sales_cagr_5y=row.sales_cagr_5y,
            profit_cagr_3y=row.profit_cagr_3y,
            profit_cagr_5y=row.profit_cagr_5y,
            as_of=row.as_of,
            notes=row.notes,
        )


class FactorRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, symbol: str) -> FactorScore | None:
        return self.session.get(FactorScore, symbol.upper())

    def map_for(self, symbols: list[str]) -> dict[str, FactorScore]:
        if not symbols:
            return {}
        wanted = {item.upper() for item in symbols}
        rows = list(self.session.scalars(select(FactorScore)))
        return {row.symbol: row for row in rows if row.symbol in wanted}

    def update_technical(
        self,
        symbol: str,
        *,
        technical,
        technical_detail: str | None,
        source: str = "tape",
    ) -> FactorScore:
        row = self.get(symbol)
        now = datetime.now()
        if row:
            row.technical = technical
            row.technical_detail = technical_detail
            row.scored_at = now
            if source:
                row.source = source
        else:
            row = FactorScore(
                symbol=symbol.upper(),
                technical=technical,
                technical_detail=technical_detail,
                scored_at=now,
                source=source,
            )
            self.session.add(row)
        self.session.flush()
        return row

    def upsert(
        self,
        symbol: str,
        *,
        quality,
        valuation,
        quality_detail: str | None,
        valuation_detail: str | None,
        source: str,
    ) -> FactorScore:
        row = self.get(symbol)
        now = datetime.now()
        if row:
            row.quality = quality
            row.valuation = valuation
            row.quality_detail = quality_detail
            row.valuation_detail = valuation_detail
            row.scored_at = now
            row.source = source
        else:
            row = FactorScore(
                symbol=symbol.upper(),
                quality=quality,
                valuation=valuation,
                quality_detail=quality_detail,
                valuation_detail=valuation_detail,
                scored_at=now,
                source=source,
            )
            self.session.add(row)
        self.session.flush()
        return row
