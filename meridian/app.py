from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from meridian import __version__
from fastapi.responses import FileResponse, Response

from meridian.api.routes import holdings as holdings_api
from meridian.api.routes import portfolio as portfolio_api
from meridian.api.routes import fundamentals as fundamentals_api
from meridian.api.routes import alerts as alerts_api
from meridian.api.routes import eod as eod_api
from meridian.api.routes import risk as risk_api
from meridian.api.routes import tape as tape_api
from meridian.config import get_settings
from meridian.logging import setup_logging
from meridian.storage.db import init_db
from meridian.ui.routes import router as ui_router

STATIC_DIR = Path(__file__).resolve().parent / "ui" / "static"


def create_app() -> FastAPI:
    setup_logging()
    init_db()
    settings = get_settings()
    app = FastAPI(
        title=settings.app.name,
        version=__version__,
        description="Local equity advisory desk. No execution.",
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(ui_router)
    app.include_router(portfolio_api.router, prefix="/api")
    app.include_router(holdings_api.router, prefix="/api")
    app.include_router(tape_api.router, prefix="/api")
    app.include_router(fundamentals_api.router, prefix="/api")
    app.include_router(risk_api.router, prefix="/api")
    app.include_router(eod_api.router, prefix="/api")
    app.include_router(alerts_api.router, prefix="/api")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(STATIC_DIR / "favicon.ico", media_type="image/x-icon")

    @app.get("/vendor/plotly.min.js", include_in_schema=False)
    def plotly_js() -> FileResponse:
        path = _plotly_path()
        if path is None:
            return Response(status_code=404)
        return FileResponse(path, media_type="application/javascript")

    return app


def _plotly_js_under(root: Path) -> tuple[Path, ...]:
    return (
        root / "package_data" / "plotly.min.js",
        root / "offline" / "plotly.min.js",
    )


def _plotly_path() -> Path | None:
    candidates: list[Path] = [STATIC_DIR / "vendor" / "plotly.min.js"]
    try:
        import plotly
    except ImportError:
        plotly = None
    if plotly is not None:
        candidates.extend(_plotly_js_under(Path(plotly.__file__).resolve().parent))

    # System `python -m meridian` will not see a venv install. Still serve
    # the JS bundled next to the project venv so charts hydrate.
    repo = Path(__file__).resolve().parents[1]
    for pattern in (
        ".venv/Lib/site-packages/plotly",
        ".venv/lib/site-packages/plotly",
        ".venv/lib/python*/site-packages/plotly",
    ):
        candidates.extend(
            js
            for root in repo.glob(pattern)
            for js in _plotly_js_under(root)
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
