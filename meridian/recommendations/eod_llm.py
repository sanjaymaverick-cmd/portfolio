from __future__ import annotations

import json
import os
from typing import Any

from loguru import logger

from meridian.recommendations.eod_rules import validate_payload
from meridian.scoring.news_filter import Headline


def llm_attribution(
    *,
    symbol: str,
    day_pct: float | None,
    headlines: list[Headline],
    nifty_chg: float | None,
    url: str,
    model: str,
    key: str | None,
) -> dict[str, Any] | None:
    if not url or not model:
        return None
    items = [
        {"title": item.title, "source": item.source, "aspect": item.aspect, "filing": item.is_filing}
        for item in headlines
        if item.kept
    ]
    prompt = {
        "role": "user",
        "content": (
            "You attribute a one-session Indian equity move. Use ONLY the headlines given. "
            "Do not invent news. Return JSON with keys positive, negative, market_context, "
            "confidence (0-1), takeaway. Each of positive/negative is a list of "
            "{driver, strength, source, aspect}.\n"
            f"symbol={symbol} day_pct={day_pct} nifty_chg={nifty_chg}\n"
            f"headlines={json.dumps(items)}"
        ),
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a research editor. Never fabricate headlines."},
            prompt,
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    token = key or os.environ.get("MERIDIAN_LLM_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        import httpx

        response = httpx.post(url, headers=headers, json=body, timeout=25)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return validate_payload(parsed, headlines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("eod llm failed: {}", exc)
        return None
