from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import httpx
from loguru import logger

from meridian.domain.money import safe_div, to_decimal

BASE = "https://www.screener.in"
SEARCH = BASE + "/api/company/search/"
HEADERS = {
    "User-Agent": "MeridianDesk/0.3 (personal research; local-only; no redistribution)",
    "Accept": "text/html,application/json",
}


@dataclass
class FundamentalSnap:
    symbol: str
    source: str = "screener"
    screener_url: str | None = None
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_cr: Decimal | None = None
    current_price: Decimal | None = None
    pe: Decimal | None = None
    book_value: Decimal | None = None
    pb: Decimal | None = None
    dividend_yield: Decimal | None = None
    roce: Decimal | None = None
    roe: Decimal | None = None
    roe_5y: Decimal | None = None
    opm: Decimal | None = None
    opm_5y_mean: Decimal | None = None
    opm_5y_std: Decimal | None = None
    debt_to_equity: Decimal | None = None
    cfo_to_op: Decimal | None = None
    ev_ebitda: Decimal | None = None
    sales_cagr_3y: Decimal | None = None
    sales_cagr_5y: Decimal | None = None
    profit_cagr_3y: Decimal | None = None
    profit_cagr_5y: Decimal | None = None
    as_of: datetime | None = None
    notes: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class ScreenerProvider:
    """Polite Screener.in reader. Structured metrics only — never stores the page."""

    def __init__(self, sleep_ms: int = 900, timeout: float = 25.0) -> None:
        self.sleep_ms = sleep_ms
        self.timeout = timeout
        self._last_call = 0.0

    def fetch(self, symbol: str) -> FundamentalSnap | None:
        try:
            url = self.resolve(symbol)
            html = self._get(url)
            if not html:
                return None
            snap = parse_company_html(html, symbol=symbol, url=url)
            return snap
        except Exception as exc:  # noqa: BLE001
            logger.warning("screener fetch failed for {}: {}", symbol, exc)
            return None

    def resolve(self, symbol: str) -> str:
        self._pace()
        try:
            response = httpx.get(
                SEARCH,
                params={"q": symbol},
                headers=HEADERS,
                timeout=self.timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            rows = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("screener search failed for {}: {}", symbol, exc)
            return f"{BASE}/company/{symbol}/consolidated/"
        target = symbol.upper()
        chosen = None
        for row in rows or []:
            path = str(row.get("url") or "")
            slug = path.strip("/").split("/")[1] if path.strip("/") else ""
            if slug.upper() == target:
                chosen = path
                break
        if chosen is None and rows:
            chosen = rows[0].get("url")
        if not chosen:
            return f"{BASE}/company/{symbol}/consolidated/"
        return urljoin(BASE, chosen)

    def _get(self, url: str) -> str | None:
        self._pace()
        response = httpx.get(url, headers=HEADERS, timeout=self.timeout, follow_redirects=True)
        if response.status_code != 200:
            logger.warning("screener HTTP {} for {}", response.status_code, url)
            return None
        return response.text

    def _pace(self) -> None:
        if self.sleep_ms <= 0:
            return
        elapsed = time.monotonic() - self._last_call
        wait = (self.sleep_ms / 1000) - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()


def parse_company_html(html: str, *, symbol: str, url: str | None = None) -> FundamentalSnap:
    ratios = _top_ratios(html)
    tables = {
        "profit-loss": _section_table(html, "profit-loss"),
        "balance-sheet": _section_table(html, "balance-sheet"),
        "cash-flow": _section_table(html, "cash-flow"),
        "ratios": _section_table(html, "ratios"),
    }
    growth = _growth_tables(html)
    sector, industry = _sector(html)

    price = _num(ratios.get("current price"))
    book = _num(ratios.get("book value"))
    market_cap = _num(ratios.get("market cap"))
    pe = _num(ratios.get("stock p/e") or ratios.get("p/e"))
    roce = _num(ratios.get("roce"))
    roe = _num(ratios.get("roe"))

    opm_series = _row_series(tables["profit-loss"], "opm %")
    opm_annual = [v for _, v in opm_series if v is not None]
    opm = opm_annual[-1] if opm_annual else None
    opm_window = opm_annual[-5:] if opm_annual else []

    borrowings = _last(tables["balance-sheet"], "borrowings")
    equity_cap = _last(tables["balance-sheet"], "equity capital")
    reserves = _last(tables["balance-sheet"], "reserves")
    book_eq = None
    if equity_cap is not None or reserves is not None:
        book_eq = (equity_cap or Decimal("0")) + (reserves or Decimal("0"))
    de = safe_div(borrowings, book_eq)

    cfo_to_op = _last(tables["cash-flow"], "cfo/op")
    if cfo_to_op is not None and cfo_to_op > 5:
        cfo_to_op = cfo_to_op / Decimal("100")
    cfo = _last(tables["cash-flow"], "cash from operating activity")
    op = _last(tables["profit-loss"], "operating profit")
    if cfo_to_op is None:
        cfo_to_op = safe_div(cfo, op)

    ev_ebitda = None
    if market_cap is not None and op not in (None, 0):
        ev = market_cap + (borrowings or Decimal("0"))
        ev_ebitda = safe_div(ev, op)

    pb = safe_div(price, book) if price and book else None

    snap = FundamentalSnap(
        symbol=symbol.upper(),
        source="screener",
        screener_url=url,
        sector=sector,
        industry=industry,
        market_cap_cr=market_cap,
        current_price=price,
        pe=pe,
        book_value=book,
        pb=pb,
        dividend_yield=_num(ratios.get("dividend yield")),
        roce=roce,
        roe=roe,
        roe_5y=_num(growth.get("return on equity", {}).get("5 years")),
        opm=opm,
        opm_5y_mean=_mean(opm_window),
        opm_5y_std=_std(opm_window),
        debt_to_equity=de,
        cfo_to_op=cfo_to_op,
        ev_ebitda=ev_ebitda,
        sales_cagr_3y=_num(growth.get("compounded sales growth", {}).get("3 years")),
        sales_cagr_5y=_num(growth.get("compounded sales growth", {}).get("5 years")),
        profit_cagr_3y=_num(growth.get("compounded profit growth", {}).get("3 years")),
        profit_cagr_5y=_num(growth.get("compounded profit growth", {}).get("5 years")),
        as_of=datetime.now(),
    )
    return snap


def _top_ratios(html: str) -> dict[str, str]:
    block = _between(html, 'id="top-ratios"', "</ul>")
    out: dict[str, str] = {}
    for item in re.findall(r"<li\b[^>]*>(.*?)</li>", block, flags=re.S | re.I):
        name_match = re.search(r'class="name">\s*(.*?)\s*</span>', item, flags=re.S)
        numbers = re.findall(r'class="number">\s*([^<]+)', item)
        if not name_match or not numbers:
            continue
        key = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", name_match.group(1))).strip().lower()
        out[key] = numbers[0].strip()
    return out


def _sector(html: str) -> tuple[str | None, str | None]:
    sector = _attr_link(html, 'title="Broad Sector"') or _attr_link(html, 'title="Sector"')
    industry = _attr_link(html, 'title="Industry"') or _attr_link(html, 'title="Broad Industry"')
    return sector, industry


def _attr_link(html: str, needle: str) -> str | None:
    idx = html.find(needle)
    if idx < 0:
        return None
    close = html.find("</a>", idx)
    chunk = html[idx:close]
    text = re.sub(r"<[^>]+>", "", chunk.split(">")[-1] if ">" in chunk else chunk)
    text = _unescape(text).strip()
    return text or None


def _growth_tables(html: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r"<th[^>]*>([^<]+)</th>\s*</tr>(.*?)</table>",
        html,
        flags=re.S | re.I,
    ):
        title = match.group(1).strip().lower()
        if "growth" not in title and title != "return on equity" and "cagr" not in title:
            continue
        body = match.group(2)
        pairs = re.findall(r"<td>([^<]+)</td>\s*<td>([^<]+)</td>", body)
        out[title] = {k.strip().lower().rstrip(":"): v.strip() for k, v in pairs}
    return out


def _section_table(html: str, section_id: str) -> list[list[str]]:
    start = html.find(f'id="{section_id}"')
    if start < 0:
        return []
    table_at = html.find("<table", start)
    if table_at < 0:
        return []
    end = html.find("</table>", table_at)
    parser = _TableParser()
    parser.feed(html[table_at : end + 8])
    return parser.rows


def _row_series(table: list[list[str]], label: str) -> list[tuple[str, Decimal | None]]:
    if not table:
        return []
    header = table[0]
    target = label.lower()
    for row in table[1:]:
        if not row:
            continue
        if _norm(row[0]) == target or _norm(row[0]).startswith(target):
            pairs: list[tuple[str, Decimal | None]] = []
            for head, cell in zip(header[1:], row[1:], strict=False):
                if _norm(head) == "ttm":
                    continue
                pairs.append((head, _num(cell)))
            return pairs
    return []


def _last(table: list[list[str]], label: str) -> Decimal | None:
    series = _row_series(table, label)
    for _, value in reversed(series):
        if value is not None:
            return value
    return None


def _num(raw: object) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).replace("\u2212", "-").replace("Cr.", "").replace("Cr", "")
    return to_decimal(text)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _std(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = _mean(values)
    if mean is None:
        return None
    var = sum((item - mean) ** 2 for item in values) / Decimal(len(values) - 1)
    return var.sqrt()


def _between(html: str, start: str, end: str) -> str:
    i = html.find(start)
    if i < 0:
        return ""
    j = html.find(end, i)
    return html[i:j] if j > i else html[i : i + 8000]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("+", "")).strip().lower()


def _unescape(text: str) -> str:
    return (
        text.replace("&amp;", "&")
        .replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell = ""
        self._in = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"td", "th"}:
            self._in = True
            self._cell = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in:
            self._row.append(re.sub(r"\s+", " ", self._cell).strip())
            self._in = False
        if tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = []

    def handle_data(self, data: str) -> None:
        if self._in:
            self._cell += data
