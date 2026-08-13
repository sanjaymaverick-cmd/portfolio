from fastapi.testclient import TestClient

from meridian.app import create_app


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
