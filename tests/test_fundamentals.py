from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from meridian.data_providers.screener import FundamentalSnap, parse_company_html
from meridian.scoring.quality import score_quality
from meridian.scoring.valuation import score_valuation

FIXTURE = Path(__file__).parent / "fixtures" / "screener_reliance.html"


def test_parse_reliance_fixture() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    snap = parse_company_html(html, symbol="RELIANCE", url="https://www.screener.in/company/RELIANCE/")
    assert snap.pe == Decimal("23.9")
    assert snap.roe == Decimal("8.91")
    assert snap.roce == Decimal("10.3")
    assert snap.current_price == Decimal("1317")
    assert snap.book_value == Decimal("668")
    assert snap.pb is not None and Decimal("1.9") < snap.pb < Decimal("2.1")
    assert snap.opm == Decimal("17")
    assert snap.debt_to_equity is not None
    assert snap.sales_cagr_5y == Decimal("18")
    assert snap.profit_cagr_5y == Decimal("12")
    assert snap.cfo_to_op is not None
    assert snap.sector == "Energy"


def test_quality_and_valuation_range() -> None:
    snap = FundamentalSnap(
        symbol="TEST",
        pe=Decimal("14"),
        pb=Decimal("2.0"),
        ev_ebitda=Decimal("9"),
        roe=Decimal("18"),
        roce=Decimal("16"),
        opm=Decimal("20"),
        opm_5y_std=Decimal("1.2"),
        debt_to_equity=Decimal("0.4"),
        cfo_to_op=Decimal("1.1"),
        sales_cagr_5y=Decimal("12"),
        sales_cagr_3y=Decimal("10"),
        profit_cagr_5y=Decimal("11"),
        profit_cagr_3y=Decimal("9"),
        sector="Energy",
    )
    quality, q_parts = score_quality(snap)
    valuation, v_parts = score_valuation(snap)
    assert quality is not None and Decimal("6") <= quality <= Decimal("9.5")
    assert valuation is not None and Decimal("4") <= valuation <= Decimal("9")
    assert all(part is not None for part in q_parts.values())
    assert v_parts["pe"] is not None


def test_missing_inputs_degrade() -> None:
    quality, parts = score_quality(FundamentalSnap(symbol="X"))
    assert quality is None
    assert all(value is None for value in parts.values())
