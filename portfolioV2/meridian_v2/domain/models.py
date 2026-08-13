from __future__ import annotations

from enum import Enum


class AssetClass(str, Enum):
    EQUITY = "equity"
    COMMODITY = "commodity"
    FX = "fx"


class WatchStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PolicyKind(str, Enum):
    INVENTORY_HEDGE = "inventory_hedge"
    VOL_HARVEST = "vol_harvest"
    VEGA_DEFENSE = "vega_defense"
    SIGNAL = "signal"
    FX_REVIEW = "fx_review"


class AckAction(str, Enum):
    ACCEPT = "accept"
    DISMISS = "dismiss"
    SNOOZE = "snooze"


class SignalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"
    LOG_ONLY = "log_only"


class RegimeLabel(str, Enum):
    CALM = "Calm"
    ELEVATED = "Elevated"
    STRESS = "Stress"


class SeriesKind(str, Enum):
    CONTINUOUS = "CONTINUOUS"
    CONTRACT = "CONTRACT"


class InstrumentType(str, Enum):
    OPTION = "option"
    FUTURE = "future"
    SPOT = "spot"
