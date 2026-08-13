from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_YAML = ROOT / "config" / "default.yaml"


class AppCfg(BaseModel):
    name: str = "MERIDIAN"
    subtitle: str = "Equity Advisory Desk · India"
    host: str = "127.0.0.1"
    port: int = 8787
    theme: str = "dark"
    open_browser: bool = True


class PathsCfg(BaseModel):
    data_dir: str = "data"
    db_filename: str = "meridian.db"
    cache_dir: str = "data/cache"
    import_dir: str = "data/imports"
    log_dir: str = "logs"


class MarketCfg(BaseModel):
    primary_exchange: str = "NSE"
    secondary_exchange: str = "BSE"
    nifty_ticker: str = "^NSEI"
    vix_ticker: str = "^INDIAVIX"
    currency: str = "INR"
    correlation_window: int = 60
    ewma_lambda: float = 0.94
    beta_shrinkage: float = 0.15
    rsi_period: int = 14
    nifty_fallback: str = "NIFTYBEES.NS"


class ProvidersCfg(BaseModel):
    yfinance_enabled: bool = True
    screener_enabled: bool = True
    screener_ttl_hours: int = 24
    screener_sleep_ms: int = 900
    price_ttl_minutes: int = 15
    history_days: int = 220
    news_ttl_minutes: int = 30
    request_sleep_ms: int = 400
    batch_size: int = 8


class RegimeCfg(BaseModel):
    mode: str = "rules"
    vix_elevated: float = 16.0
    vix_stress: float = 22.0


class ScoringCfg(BaseModel):
    scale_min: int = 0
    scale_max: int = 10


class UiCfg(BaseModel):
    compact_threshold_lakhs: float = 10
    default_page_size: int = 200


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MERIDIAN_", extra="ignore")

    app: AppCfg = Field(default_factory=AppCfg)
    paths: PathsCfg = Field(default_factory=PathsCfg)
    market: MarketCfg = Field(default_factory=MarketCfg)
    providers: ProvidersCfg = Field(default_factory=ProvidersCfg)
    regime: RegimeCfg = Field(default_factory=RegimeCfg)
    scoring: ScoringCfg = Field(default_factory=ScoringCfg)
    ui: UiCfg = Field(default_factory=UiCfg)

    @property
    def data_dir(self) -> Path:
        path = Path(self.paths.data_dir)
        return path if path.is_absolute() else ROOT / path

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.paths.db_filename

    @property
    def cache_dir(self) -> Path:
        path = Path(self.paths.cache_dir)
        return path if path.is_absolute() else ROOT / path

    @property
    def import_dir(self) -> Path:
        path = Path(self.paths.import_dir)
        return path if path.is_absolute() else ROOT / path

    @property
    def log_dir(self) -> Path:
        path = Path(self.paths.log_dir)
        return path if path.is_absolute() else ROOT / path

    def ensure_dirs(self) -> None:
        for folder in (self.data_dir, self.cache_dir, self.import_dir, self.log_dir):
            folder.mkdir(parents=True, exist_ok=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    payload = _load_yaml(DEFAULT_YAML)
    user = ROOT / "config" / "local.yaml"
    if user.exists():
        merged = _deep_merge(payload, _load_yaml(user))
    else:
        merged = payload
    settings = Settings.model_validate(merged)
    settings.ensure_dirs()
    return settings


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
