from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import httpx
from loguru import logger

from meridian.scoring.news_filter import Headline

HEADERS = {
    "User-Agent": "MeridianDesk/0.7 (personal research; local-only)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}


def fetch_symbol_news(symbol: str, company: str | None, *, sleep_ms: int = 400) -> list[Headline]:
    query = " ".join(part for part in (symbol, _short_name(company), "NSE") if part)
    urls = [
        f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en",
        "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml",
    ]
    out: list[Headline] = []
    for url in urls:
        try:
            out.extend(_read_rss(url, filing="nsearchives" in url or "nseindia" in url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("rss failed {}: {}", url, exc)
        if sleep_ms:
            time.sleep(sleep_ms / 1000)
    if symbol:
        out = [item for item in out if _loose_match(item, symbol, company) or item.is_filing]
    return out


def _read_rss(url: str, *, filing: bool) -> list[Headline]:
    response = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
    if response.status_code != 200:
        logger.warning("rss HTTP {} {}", response.status_code, url)
        return []
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return []
    items: list[Headline] = []
    for node in root.iter():
        if node.tag.lower().endswith("item"):
            title = _child(node, "title")
            link = _child(node, "link")
            source = _child(node, "source") or ("NSE" if filing else "Google News")
            pub = _parse_date(_child(node, "pubDate") or _child(node, "published"))
            if title:
                items.append(
                    Headline(
                        title=title,
                        url=link,
                        source=source,
                        published=pub,
                        is_filing=filing,
                    )
                )
    return items[:40]


def _child(node: ET.Element, name: str) -> str | None:
    for child in node:
        if child.tag.lower().endswith(name.lower()):
            return (child.text or "").strip() or None
    return None


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return None


def _short_name(company: str | None) -> str:
    if not company:
        return ""
    return company.replace("Limited", "").replace("Ltd", "").replace("India", "").strip()


def _loose_match(item: Headline, symbol: str, company: str | None) -> bool:
    hay = item.title.lower()
    if symbol.lower() in hay:
        return True
    token = _short_name(company).split(" ")[0].lower() if company else ""
    return bool(token) and len(token) > 3 and token in hay
