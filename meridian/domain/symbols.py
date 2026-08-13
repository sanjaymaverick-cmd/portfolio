from __future__ import annotations

import re
from dataclasses import dataclass

_SUFFIXES = (
    ".NS",
    ".BO",
    ".BSE",
    ".NSE",
    "-EQ",
    "-BE",
    "-BL",
    "-BZ",
    "-SM",
)
_SPACE_ALIASES = {
    "HDFC BANK": "HDFCBANK",
    "ICICI BANK": "ICICIBANK",
    "KOTAK BANK": "KOTAKBANK",
    "AXIS BANK": "AXISBANK",
    "SBI": "SBIN",
    "L&T": "LT",
    "LARSEN & TOUBRO": "LT",
    "BAJAJ FINANCE": "BAJFINANCE",
    "BAJAJ FINSERV": "BAJAJFINSV",
    "ASIAN PAINTS": "ASIANPAINT",
    "BHARTI AIRTEL": "BHARTIARTL",
    "NESTLE": "NESTLEIND",
    "ULTRATECH": "ULTRACEMCO",
    "ULTRATECH CEMENT": "ULTRACEMCO",
    "SUN PHARMA": "SUNPHARMA",
    "TATA MOTORS": "TATAMOTORS",
    "TATA STEEL": "TATASTEEL",
    "HINDUNILVR": "HINDUNILVR",
    "HUL": "HINDUNILVR",
    "INFOSYS": "INFY",
    "TCS": "TCS",
    "RELIANCE INDUSTRIES": "RELIANCE",
}


@dataclass(frozen=True, slots=True)
class ParsedSymbol:
    symbol: str
    exchange: str
    yahoo: str


def normalize_symbol(raw: object, default_exchange: str = "NSE") -> ParsedSymbol:
    text = str(raw or "").strip().upper()
    text = text.replace("\u00a0", " ")
    exchange = default_exchange.upper()
    if text.endswith(".BO") or text.endswith(".BSE"):
        exchange = "BSE"
    elif text.endswith(".NS") or text.endswith(".NSE"):
        exchange = "NSE"
    for suffix in _SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    text = re.sub(r"\s+", " ", text).strip()
    text = _SPACE_ALIASES.get(text, text)
    if " " in text and text.replace(" ", "") in _SPACE_ALIASES.values():
        text = text.replace(" ", "")
    compact = re.sub(r"[^A-Z0-9&-]", "", text.replace(" ", ""))
    symbol = compact or "UNKNOWN"
    yahoo = f"{symbol}.BO" if exchange == "BSE" else f"{symbol}.NS"
    return ParsedSymbol(symbol=symbol, exchange=exchange, yahoo=yahoo)


def yahoo_candidates(symbol: str, exchange: str, resolved: str | None = None) -> list[str]:
    primary = f"{symbol}.BO" if exchange.upper() == "BSE" else f"{symbol}.NS"
    secondary = f"{symbol}.NS" if exchange.upper() == "BSE" else f"{symbol}.BO"
    ordered: list[str] = []
    for ticker in (resolved, primary, secondary):
        if ticker and ticker not in ordered:
            ordered.append(ticker)
    return ordered


def normalize_isin(raw: object) -> str | None:
    text = str(raw or "").strip().upper()
    if re.fullmatch(r"INE[A-Z0-9]{9}", text):
        return text
    return None
