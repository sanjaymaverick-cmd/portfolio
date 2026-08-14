from __future__ import annotations

from types import SimpleNamespace
from datetime import date

from meridian_v2.domain.templates import CATALOG, catalog_payload
from meridian_v2.signals.chart_payload import (
    ChartLevel,
    ChartMarker,
    ChartWindow,
    ChartZone,
    build_chart_payload,
)


def test_payload_has_overlays_and_no_model_fields():
    bars = [
        SimpleNamespace(bar_date=date(2026, 8, 1), open=100, high=104, low=99, close=103, volume=10),
        SimpleNamespace(bar_date=date(2026, 8, 4), open=103, high=108, low=102, close=107, volume=12),
        SimpleNamespace(bar_date=date(2026, 8, 5), open=107, high=109, low=105, close=106, volume=8),
        SimpleNamespace(bar_date=date(2026, 8, 6), open=106, high=110, low=105, close=109, volume=9),
        SimpleNamespace(bar_date=date(2026, 8, 7), open=109, high=111, low=108, close=110, volume=11),
    ]
    payload = build_chart_payload(
        symbol="GOLD",
        label="GOLD CONTINUOUS",
        quality="proxy",
        bars=bars,
        markers=[ChartMarker("2026-08-07", "long", "Look at a long / entry", 72)],
        levels=[ChartLevel(108.0, "Slow average")],
        zones=[ChartZone(99.0, 111.0, "Recent range")],
        windows=[ChartWindow("2026-08-04", "2026-08-07", "Higher-attention window")],
    ).as_dict()
    assert payload["markers"][0]["shape"] == "diamond"
    assert payload["markers"][0]["color"] == "#4A9B7F"
    assert "72" in payload["markers"][0]["text"]
    assert payload["zones"][0]["title"] == "Recent range"
    assert payload["windows"][0]["start"] == "2026-08-04"
    assert payload["signal"]
    assert "weights" not in payload
    assert "shap" not in payload
    assert payload["legend"]["long"].startswith("Green diamond")


def test_catalog_covers_every_required_scenario():
    body = catalog_payload()
    keys = {item["key"] for item in body["scenarios"]}
    assert keys == set(CATALOG)
    assert all("(not an order)" in item["title"].lower() for item in body["scenarios"])
    assert [item["key"] for item in body["vega_actions"]] == [
        "limit_cap",
        "cut_options",
        "hedge_options",
        "book_balance",
        "regime_limit",
        "time_reduce",
    ]
