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
    name: str = "MERIDIAN V2"
    subtitle: str = "Research & hedge-review desk · India"
    host: str = "127.0.0.1"
    port: int = 8766
    theme: str = "dark"
    open_browser: bool = True


class PathsCfg(BaseModel):
    data_dir: str = "~/MeridianV2"
    db_filename: str = "meridian_v2.db"
    log_dir: str = "~/MeridianV2/logs"


class WatchlistCfg(BaseModel):
    active_cap: int = 50


class ModulesCfg(BaseModel):
    watchlist: bool = True
    mcx: bool = True
    signals: bool = True
    journal: bool = True
    fx: bool = True
    inventory_hedge: bool = True
    vol_harvest: bool = True
    vega_defense: bool = True
    alerts: bool = True


class AlertsCfg(BaseModel):
    poll_seconds: int = 60
    min_days_between_prompts: int = 2
    snooze_hours: int = 24


class RegimeCfg(BaseModel):
    default_label: str = "Elevated"


class SymbolInventoryCfg(BaseModel):
    h_star: float = 0.50
    min_lots: float = 1.0
    ratio_tol: float = 0.10
    lot_step: float = 1.0
    gamma_warn_abs: float = 0.0
    enabled: bool = True


class VolHarvestCfg(BaseModel):
    min_lots: float = 1.0
    lot_step: float = 1.0
    ratio_tol: float = 0.10


class VegaSymbolCfg(BaseModel):
    vega_limit: float = 200_000
    warn_utilization: float = 0.80
    nu_star: float = 0.0
    lot_step: float = 1.0
    hedge_vega_per_lot: float = 55_000
    hedge_delta: float = 0.48
    enabled: bool = True


class HedgeCfg(BaseModel):
    roll_blackout_days: int = 3
    min_days_between_prompts: int = 2
    inventory: dict[str, SymbolInventoryCfg] = Field(default_factory=dict)
    vol_harvest: VolHarvestCfg = Field(default_factory=VolHarvestCfg)
    vega: dict[str, VegaSymbolCfg] = Field(default_factory=dict)


class ProvidersCfg(BaseModel):
    yfinance_enabled: bool = True
    price_ttl_minutes: int = 15
    request_sleep_ms: int = 400


class FxCfg(BaseModel):
    pairs: list[str] = Field(default_factory=lambda: ["USDINR", "EURUSD", "USDJPY"])
    move_review_pct: float = 1.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MERIDIAN_V2_", extra="ignore")

    app: AppCfg = Field(default_factory=AppCfg)
    paths: PathsCfg = Field(default_factory=PathsCfg)
    watchlist: WatchlistCfg = Field(default_factory=WatchlistCfg)
    modules: ModulesCfg = Field(default_factory=ModulesCfg)
    alerts: AlertsCfg = Field(default_factory=AlertsCfg)
    regime: RegimeCfg = Field(default_factory=RegimeCfg)
    hedge: HedgeCfg = Field(default_factory=HedgeCfg)
    providers: ProvidersCfg = Field(default_factory=ProvidersCfg)
    fx: FxCfg = Field(default_factory=FxCfg)
    test_db: str | None = None

    @property
    def data_dir(self) -> Path:
        return Path(self.paths.data_dir).expanduser()

    @property
    def db_path(self) -> Path:
        if self.test_db:
            return Path(self.test_db)
        return self.data_dir / self.paths.db_filename

    @property
    def log_dir(self) -> Path:
        return Path(self.paths.log_dir).expanduser()

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    payload = _load_yaml(DEFAULT_YAML)
    user = ROOT / "config" / "local.yaml"
    if user.exists():
        payload = _deep_merge(payload, _load_yaml(user))
    settings = Settings.model_validate(payload)
    settings.ensure_dirs()
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()
