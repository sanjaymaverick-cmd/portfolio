from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from meridian import __version__
from fastapi.responses import FileResponse, Response

from meridian.api.routes import holdings as holdings_api
from meridian.api.routes import portfolio as portfolio_api
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

    @app.get("/vendor/plotly.min.js", include_in_schema=False)
    def plotly_js() -> FileResponse:
        path = _plotly_path()
        if path is None:
            return Response(status_code=404)
        return FileResponse(path, media_type="application/javascript")

    return app


def _plotly_path() -> Path | None:
    try:
        import plotly
    except ImportError:
        return None
    root = Path(plotly.__file__).resolve().parent
    for candidate in (
        root / "package_data" / "plotly.min.js",
        root / "offline" / "plotly.min.js",
    ):
        if candidate.exists():
            return candidate
    return None
