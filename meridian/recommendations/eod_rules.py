from __future__ import annotations

import re
from typing import Any

from meridian.scoring.news_filter import Headline


def rule_attribution(
    *,
    symbol: str,
    day_pct: float | None,
    headlines: list[Headline],
    nifty_chg: float | None,
) -> dict[str, Any]:
    positives: list[dict[str, Any]] = []
    negatives: list[dict[str, Any]] = []
    for item in headlines:
        if not item.kept:
            continue
        driver = {
            "driver": item.title,
            "strength": round(min(1.0, abs(item.sentiment) / 2 + (0.25 if item.is_filing else 0)), 2),
            "source": item.source,
            "aspect": item.aspect,
        }
        if item.sentiment > 0.05:
            positives.append(driver)
        elif item.sentiment < -0.05:
            negatives.append(driver)
        elif item.is_filing:
            (positives if (day_pct or 0) >= 0 else negatives).append(driver)
    positives.sort(key=lambda row: row["strength"], reverse=True)
    negatives.sort(key=lambda row: row["strength"], reverse=True)
    if headlines:
        lead = headlines[0].title
        takeaway = f"{symbol} {_move_words(day_pct)}. News: {lead}"
    else:
        takeaway = f"{symbol} {_move_words(day_pct)}. No useful company news found for today."
    market = market_line(nifty_chg, day_pct)
    n = len([h for h in headlines if h.kept])
    confidence = 0.35 if n == 0 else min(0.78, 0.42 + 0.06 * n)
    return {
        "positive": positives[:4],
        "negative": negatives[:4],
        "market_context": market,
        "confidence": round(confidence, 2),
        "takeaway": takeaway,
    }


def validate_payload(
    payload: dict[str, Any], headlines: list[Headline] | None = None
) -> dict[str, Any]:
    pos = payload.get("positive") if isinstance(payload.get("positive"), list) else []
    neg = payload.get("negative") if isinstance(payload.get("negative"), list) else []
    clean_pos = [row for item in pos if (row := _driver(item, headlines))]
    clean_neg = [row for item in neg if (row := _driver(item, headlines))]
    try:
        conf = float(payload.get("confidence", 0.4))
    except (TypeError, ValueError):
        conf = 0.4
    takeaway = str(payload.get("takeaway") or "").strip() or "No takeaway."
    context = str(payload.get("market_context") or "").strip()
    return {
        "positive": clean_pos[:4],
        "negative": clean_neg[:4],
        "market_context": context,
        "confidence": max(0.0, min(1.0, conf)),
        "takeaway": takeaway[:400],
    }


def _driver(item: object, headlines: list[Headline] | None = None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    text = str(item.get("driver") or "").strip()
    if not text:
        return None
    if headlines is not None and not _cites_known(text, headlines):
        return None
    try:
        strength = float(item.get("strength", 0.3))
    except (TypeError, ValueError):
        strength = 0.3
    return {
        "driver": text[:280],
        "strength": max(0.0, min(1.0, strength)),
        "source": str(item.get("source") or "unknown")[:80],
        "aspect": str(item.get("aspect") or "Other")[:24],
    }


def engine_label(engine: str | None) -> str:
    key = (engine or "rules").lower()
    if key == "llm":
        return "From headlines (AI)"
    return "From headlines"


def why_label(why: str | None) -> str | None:
    return {
        "threshold": "moved more than 1.5%",
        "contribution": "large rupee move",
    }.get(why or "", why)


def market_line(nifty_chg: float | None, day_pct: float | None) -> str:
    if nifty_chg is None:
        return "Nifty figure not available."
    nifty = _nifty_words(nifty_chg)
    if day_pct is not None and abs(day_pct) > abs(nifty_chg) + 0.8:
        return f"{nifty} This stock moved more than Nifty — look at company news, not just the market."
    if day_pct is not None and day_pct * nifty_chg > 0:
        return f"{nifty} It moved the same way as Nifty."
    return nifty


def simplify_market(text: str | None) -> str | None:
    if not text:
        return text
    out = text
    out = out.replace("Nifty context unavailable.", "Nifty figure not available.")
    out = re.sub(
        r"Nifty session ([+-]?\d+(?:\.\d+)?)%\.",
        lambda match: _nifty_words(float(match.group(1))),
        out,
    )
    out = out.replace(
        " Move is name-specific versus the index.",
        " This stock moved more than Nifty — look at company news, not just the market.",
    )
    out = out.replace(" Direction aligns with the tape.", " It moved the same way as Nifty.")
    return out


def simplify_takeaway(text: str | None) -> str | None:
    if not text:
        return text
    out = text.replace("Cited:", "News:")
    out = out.replace(
        "No same-day headlines cleared the relevance gate.",
        "No useful company news found for today.",
    )
    out = re.sub(
        r" higher \(([+-]?\d+(?:\.\d+)?)%\)",
        lambda match: f" rose {abs(float(match.group(1))):.2f}%",
        out,
    )
    out = re.sub(
        r" lower \(([+-]?\d+(?:\.\d+)?)%\)",
        lambda match: f" fell {abs(float(match.group(1))):.2f}%",
        out,
    )
    out = re.sub(r" unchanged \(([+-]?\d+(?:\.\d+)?)%\)", r" was unchanged (\1%)", out)
    return out


def _move_words(day_pct: float | None) -> str:
    if day_pct is None:
        return "price not marked"
    if day_pct > 0:
        return f"rose {day_pct:.2f}%"
    if day_pct < 0:
        return f"fell {abs(day_pct):.2f}%"
    return "was unchanged"


def _nifty_words(nifty_chg: float) -> str:
    if nifty_chg > 0.05:
        return f"Nifty was up {nifty_chg:.2f}% today."
    if nifty_chg < -0.05:
        return f"Nifty was down {abs(nifty_chg):.2f}% today."
    return f"Nifty was almost flat today ({nifty_chg:+.2f}%)."


def _cites_known(text: str, headlines: list[Headline]) -> bool:
    hay = text.lower()
    for item in headlines:
        title = (item.title or "").lower()
        if not title:
            continue
        if title in hay or hay in title:
            return True
        tokens = [tok for tok in re.findall(r"[a-z0-9]+", title) if len(tok) > 3]
        if tokens and sum(1 for tok in tokens if tok in hay) >= min(3, len(tokens)):
            return True
    return False
