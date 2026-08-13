from pathlib import Path

from meridian.ingestion.columns import detect_broker, infer_mapping
from meridian.ingestion.service import parse_statement
from meridian.ingestion.normalize import map_rows

FIXTURES = Path(__file__).parent / "fixtures"


def test_zerodha_csv() -> None:
    headers, records = parse_statement(FIXTURES / "zerodha_holdings.csv")
    assert detect_broker(headers, "zerodha_holdings.csv") == "zerodha"
    rows = map_rows(records, infer_mapping(headers))
    assert [row.symbol for row in rows] == ["RELIANCE", "HDFCBANK", "INFY"]
    assert all(row.error is None for row in rows)
    assert rows[0].quantity == 50
    assert rows[0].last_price is not None


def test_angel_and_groww() -> None:
    headers, records = parse_statement(FIXTURES / "angel_holdings.csv")
    assert detect_broker(headers, "angel_one.xlsx") == "angel_one"
    angel = map_rows(records, infer_mapping(headers))
    assert {row.symbol for row in angel} == {"TCS", "ITC"}

    headers, records = parse_statement(FIXTURES / "groww_holdings.csv")
    groww = map_rows(records, infer_mapping(headers))
    assert {row.symbol for row in groww} == {"INFY", "HDFCBANK"}
    assert all(row.error is None for row in groww)


def test_generic_headers() -> None:
    headers, records = parse_statement(FIXTURES / "generic_holdings.csv")
    rows = map_rows(records, infer_mapping(headers))
    assert rows[0].sector == "Telecom"
    assert rows[1].symbol == "SUNPHARMA"
