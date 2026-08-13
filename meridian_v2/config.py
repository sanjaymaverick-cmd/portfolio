"""V2 settings — distinct DB and port from v1."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_db() -> Path:
    return Path.home() / ".meridian_v2" / "meridian_v2.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MERIDIAN_V2_",
        env_file=".env.v2",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Field(default_factory=_default_db)
    host: str = "127.0.0.1"
    port: int = 8766
    watchlist_active_cap: int = 50
    app_title: str = "MERIDIAN V2"


@lru_cache
def get_settings() -> Settings:
    return Settings()
