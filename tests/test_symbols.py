from meridian.domain.symbols import normalize_symbol, yahoo_candidates


def test_yahoo_suffix_and_aliases() -> None:
    assert normalize_symbol("RELIANCE.NS").yahoo == "RELIANCE.NS"
    assert normalize_symbol("TCS.BO").exchange == "BSE"
    assert normalize_symbol("HDFC BANK").symbol == "HDFCBANK"
    assert normalize_symbol("Infosys").symbol == "INFY"
    assert normalize_symbol("SBI").symbol == "SBIN"
    assert yahoo_candidates("RELIANCE", "NSE") == ["RELIANCE.NS", "RELIANCE.BO"]
    assert yahoo_candidates("TCS", "BSE", "TCS.NS") == ["TCS.NS", "TCS.BO"]
