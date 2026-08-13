"""FastAPI factory for MERIDIAN V2 (stub)."""

from __future__ import annotations

from fastapi import FastAPI

from meridian_v2 import __version__
from meridian_v2.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_title, version=__version__)

    @app.get("/health")
    def health() -> dict:
        return {
            "app": "meridian_v2",
            "version": __version__,
            "db_path": str(settings.db_path),
            "broker_execution": False,
        }

    return app
