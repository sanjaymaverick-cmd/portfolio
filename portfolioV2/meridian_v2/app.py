from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from meridian_v2 import __version__
from meridian_v2.api.routes import router as api_router
from meridian_v2.config import get_settings
from meridian_v2.storage.db import init_db
from meridian_v2.ui.routes import router as ui_router

STATIC_DIR = Path(__file__).resolve().parent / "ui" / "static"


def create_app() -> FastAPI:
    init_db()
    settings = get_settings()
    app = FastAPI(
        title=settings.app.name,
        version=__version__,
        description="MERIDIAN V2 research desk. Isolated from v1. Advisor only — no execution.",
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(ui_router)
    app.include_router(api_router, prefix="/api")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(STATIC_DIR / "favicon.ico", media_type="image/x-icon")

    return app
