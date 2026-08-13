from __future__ import annotations

from enum import Enum


class AssetClass(str, Enum):
    EQUITY = "equity"
    COMMODITY = "commodity"
    FX = "fx"


class RegimeLabel(str, Enum):
    CALM = "Calm"
    ELEVATED = "Elevated"
    STRESS = "Stress"


class PolicyKind(str, Enum):
    INVENTORY_HEDGE = "inventory_hedge"
    VOL_HARVEST = "vol_harvest"
    VEGA_DEFENSE = "vega_defense"
