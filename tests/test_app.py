from fastapi.testclient import TestClient

from meridian.app import _plotly_path, create_app


def test_desk_pages_render() -> None:
    client = TestClient(create_app())
    for path in ("/", "/holdings", "/import", "/risk", "/alerts", "/settings"):
        response = client.get(path)
        assert response.status_code == 200
        assert "MERIDIAN" in response.text
    assert client.get("/api/health").json()["status"] == "ok"
    tape = client.get("/api/tape")
    assert tape.status_code == 200
    assert "stale" in tape.json()
    missing = client.get("/api/fundamentals/NOSUCH")
    assert missing.status_code == 200
    assert missing.json()["status"] == "missing"
    eod = client.get("/api/eod/movers")
    assert eod.status_code == 200
    assert "movers" in eod.json()
    alerts = client.get("/api/alerts")
    assert alerts.status_code == 200
    assert "open" in alerts.json()


def test_holding_detail_embeds_candlestick_after_plotly_js() -> None:
    html = TestClient(create_app()).get("/holdings/1").text
    assert "No price history yet" not in html
    assert 'data-chart-url="/api/holdings/1/chart"' in html
    assert "lightweight-charts.js" in html
    js = html.find('src="/static/vendor/lightweight-charts.js"')
    hook = html.find("data-chart-url")
    assert 0 <= js < hook


def test_favicon_is_served() -> None:
    client = TestClient(create_app())
    ico = client.get("/favicon.ico")
    assert ico.status_code == 200
    assert ico.content[:4] == b"\x00\x00\x01\x00"
    svg = client.get("/static/favicon.svg")
    assert svg.status_code == 200
    assert "<svg" in svg.text
    html = client.get("/").text
    assert 'rel="icon"' in html
    assert "/favicon.ico" in html


def test_holding_chart_payload() -> None:
    payload = TestClient(create_app()).get("/api/holdings/1/chart").json()
    assert payload["symbol"]
    assert "candles" in payload


def test_plotly_vendor_js_is_served() -> None:
    path = _plotly_path()
    assert path is not None
    assert path.is_file()
    response = TestClient(create_app()).get("/vendor/plotly.min.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert len(response.content) > 1000
