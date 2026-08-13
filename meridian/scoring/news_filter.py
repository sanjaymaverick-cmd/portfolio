from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

ASPECTS: dict[str, tuple[str, ...]] = {
    "Results": ("result", "profit", "revenue", "earning", "ebitda", "guidance", "eps", "q1", "q2", "q3", "q4"),
    "Ownership": ("promoter", "fii", "dii", "stake", "pledged", "buyback", "block deal", "bulk deal"),
    "Management": ("ceo", "managing director", "chairman", "resign", "appoint", "cfo", "board"),
    "Regulatory": ("sebi", "rbi", "nclat", "penalty", "approval", "license", "probe", "fine"),
    "Order": ("order win", "wins order", "contract", "tender", "award", "bagged"),
}

_POS = (
    "beat",
    "surge",
    "jump",
    "win",
    "upgrade",
    "record",
    "approval",
    "profit",
    "growth",
    "strong",
    "raise",
    "buy",
)
_NEG = (
    "miss",
    "fall",
    "slump",
    "downgrade",
    "probe",
    "penalty",
    "resign",
    "loss",
    "pledge",
    "weak",
    "cut",
    "fraud",
    "delay",
)
_NEGATORS = (
    "not ",
    "no ",
    "never ",
    "failed to",
    "missed",
    "short of",
    "didn't",
    "did not",
    "cannot",
    "without ",
    "unable to",
    "fails to",
)
_DIM = ("slightly", "modestly", "marginally", "only", "somewhat", "nearly")
_FILING = ("nse", "bse", "exchange filing", "sebi", "corporate announcement", "outcome of board")

_STOP = {"ltd", "limited", "india", "the", "and", "of", "inc", "plc", "industries", "company"}


@dataclass
class Headline:
    title: str
    url: str | None = None
    source: str = "rss"
    published: datetime | None = None
    sentiment: float = 0.0
    aspect: str = "Other"
    rank: float = 0.0
    is_filing: bool = False
    kept: bool = False
    relevant: bool = False


def clean_title(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fingerprint(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_title(title).lower())


def is_relevant(title: str, symbol: str, company: str | None) -> bool:
    hay = title.lower()
    if symbol.lower() in hay:
        return True
    tokens = [t for t in re.findall(r"[a-z0-9]+", (company or "").lower()) if t not in _STOP and len(t) > 2]
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in hay)
    return hits >= min(2, len(tokens))


def tag_aspect(title: str) -> str:
    hay = title.lower()
    for aspect, keys in ASPECTS.items():
        if any(key in hay for key in keys):
            return aspect
    return "Other"


def is_filing(title: str, source: str) -> bool:
    hay = f"{title} {source}".lower()
    return any(token in hay for token in _FILING)


def sentiment_score(title: str) -> float:
    text = f" {clean_title(title).lower()} "
    score = 0.0
    for word in _POS:
        for match in re.finditer(rf"\b{re.escape(word)}", text):
            score += _signed(text, match.start(), +1.0)
    for word in _NEG:
        for match in re.finditer(rf"\b{re.escape(word)}", text):
            score += _signed(text, match.start(), -1.0)
    return max(-2.0, min(2.0, score))


def _signed(text: str, index: int, base: float) -> float:
    window = text[max(0, index - 24) : index]
    if any(neg in window for neg in _NEGATORS):
        base *= -1.0
    if any(dim in window for dim in _DIM):
        base *= 0.45
    return base


def source_quality(source: str, filing: bool) -> float:
    if filing:
        return 1.4
    low = source.lower()
    if any(name in low for name in ("nse", "bse", "sebi", "exchange")):
        return 1.3
    if any(name in low for name in ("reuters", "bloomberg", "hindu", "mint", "economic times")):
        return 1.1
    return 1.0


def rank_item(item: Headline) -> float:
    impact = 1.25 if item.aspect in {"Results", "Regulatory", "Order"} else 1.0
    return abs(item.sentiment) * source_quality(item.source, item.is_filing) * impact + (0.8 if item.is_filing else 0.0)


def filter_headlines(
    raw: list[Headline],
    *,
    symbol: str,
    company: str | None,
    keep: int = 6,
) -> list[Headline]:
    seen: set[str] = set()
    scored: list[Headline] = []
    for item in raw:
        item.title = clean_title(item.title)
        if not item.title:
            continue
        key = fingerprint(item.title)
        if key in seen:
            continue
        seen.add(key)
        item.relevant = is_relevant(item.title, symbol, company)
        if not item.relevant:
            continue
        item.aspect = tag_aspect(item.title)
        item.is_filing = item.is_filing or is_filing(item.title, item.source)
        item.sentiment = sentiment_score(item.title)
        item.rank = rank_item(item)
        scored.append(item)
    scored.sort(key=lambda item: item.rank, reverse=True)
    kept: list[Headline] = []
    for item in scored:
        if item.is_filing or len(kept) < keep:
            item.kept = True
            kept.append(item)
    return kept
