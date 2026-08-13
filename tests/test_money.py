from decimal import Decimal

from meridian.domain.money import format_inr, format_pct, format_qty, indian_comma, to_decimal


def test_indian_comma() -> None:
    assert indian_comma(Decimal("1234567.89")) == "12,34,567.89"
    assert indian_comma(Decimal("999")) == "999.00"
    assert indian_comma(Decimal("1234")) == "1,234.00"


def test_format_inr_compact() -> None:
    assert format_inr(Decimal("4820000"), compact=True) == "₹48.20 L"
    assert format_inr(Decimal("25000000"), compact=True) == "₹2.50 Cr"
    assert format_inr(Decimal("-1500000"), compact=True, signed=True) == "-₹15.00 L"


def test_signed_pct_and_qty() -> None:
    assert format_pct(Decimal("15.64")) == "+15.64%"
    assert format_pct(Decimal("-2.1")) == "-2.10%"
    assert format_qty(Decimal("1250")) == "1,250"


def test_to_decimal_parses_broker_noise() -> None:
    assert to_decimal("₹1,23,456.78") == Decimal("123456.78")
    assert to_decimal("(1,200.50)") == Decimal("-1200.50")
    assert to_decimal("—") is None
