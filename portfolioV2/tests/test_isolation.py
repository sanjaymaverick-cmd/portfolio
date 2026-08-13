from __future__ import annotations

import sys

from fastapi.testclient import TestClient


def test_v2_does_not_import_v1_package():
    sys.modules.pop("meridian", None)
    import meridian_v2.app  # noqa: F401

    assert "meridian" not in sys.modules or not getattr(sys.modules.get("meridian"), "__file__", "").endswith(
        "portfolio\\meridian\\__init__.py"
    )
    # Stronger: v2 package files must not import meridian.
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "meridian_v2"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("from meridian ") or stripped.startswith("import meridian"):
                offenders.append(str(path))
            if stripped.startswith("from meridian.") or stripped.startswith("import meridian."):
                offenders.append(str(path))
    assert offenders == []


def test_pages_render(session):
    from meridian_v2.app import create_app
    from meridian_v2.storage.seed import seed_demo

    seed_demo(session)
    session.commit()
    client = TestClient(create_app())
    for path in ("/", "/watch", "/signals", "/journal", "/hedge", "/harvest", "/vega", "/commodities", "/help"):
        response = client.get(path)
        assert response.status_code == 200, path
    assert "MERIDIAN V2" in client.get("/").text
    assert "MERIDIAN V2" in client.get("/api/health").json()["app"]
    assert client.get("/api/health").json()["port"] == 8766
