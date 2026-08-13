from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from meridian.config import RegimeCfg, Settings
from meridian.risk.ewma_variance import EwmaVariance
from meridian.risk.kalman_trend import KalmanTrend
from meridian.scoring.regime import RegimeInputs, apply_hysteresis, decide, raw_candidate
from meridian.scoring.regime_service import RegimeInputService
from meridian.storage.schema import Base, PriceBar


def test_ewma_vol_rises_after_high_vol() -> None:
    filt = EwmaVariance(lam=0.94)
    filt.update_series([0.002] * 40)
    calm = filt.vol_ann
    filt.update_series([0.03, -0.04, 0.035, -0.03, 0.04] * 4)
    assert filt.vol_ann > calm


def test_kalman_trend_follows_drift() -> None:
    up = KalmanTrend()
    price = 100.0
    for _ in range(80):
        price *= 1.004
        up.update(price)
    down = KalmanTrend()
    price = 100.0
    for _ in range(80):
        price *= 0.996
        down.update(price)
    assert up.trend > 0
    assert down.trend < 0
    assert up.trend_ann_pct > 0
    dumped = KalmanTrend.from_dict(up.to_dict())
    assert math.isclose(dumped.trend, up.trend, rel_tol=1e-9)


def test_hysteresis_ignores_one_day_flicker() -> None:
    cfg = RegimeCfg(confirmation_days=2, min_hold_days=1)
    calm_in = _inputs(vix=12.0)
    stress_in = _inputs(vix=22.0)
    first = decide(stress_in, cfg, current="Calm", since=datetime(2026, 8, 1).date(), pending=None, pending_days=0)
    assert first.label == "Calm"
    assert first.pending == "Stress"
    second = decide(
        _inputs(vix=12.0, as_of=datetime(2026, 8, 12)),
        cfg,
        current="Calm",
        since=datetime(2026, 8, 1).date(),
        pending="Stress",
        pending_days=1,
    )
    assert second.label == "Calm"
    stay = apply_hysteresis("Stress", "Calm", _inputs(vix=18.5), cfg)
    assert stay == "Stress"
    leave = apply_hysteresis("Stress", "Elevated", _inputs(vix=16.0), cfg)
    assert leave == "Elevated"


def test_build_regime_inputs_from_sqlite(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'reg.db'}", future=True)
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine, future=True)()
    start = datetime(2025, 10, 1)
    nifty = 22000.0
    vix = 13.0
    for day in range(120):
        nifty *= 1.001
        vix = 13.0 + 0.02 * day
        when = start + timedelta(days=day)
        session.add(
            PriceBar(
                yahoo="^NSEI",
                bar_date=when,
                open=nifty,
                high=nifty,
                low=nifty,
                close=nifty,
                volume=0,
            )
        )
        session.add(
            PriceBar(
                yahoo="^INDIAVIX",
                bar_date=when,
                open=vix,
                high=vix,
                low=vix,
                close=vix,
                volume=0,
            )
        )
    session.commit()
    service = RegimeInputService(session, settings=Settings())
    inputs = service.build_regime_inputs(datetime(2026, 1, 28), persist=True, hydrate=False)
    assert inputs.nifty_close is not None
    assert inputs.ewma_vol_ann is not None and inputs.ewma_vol_ann > 0
    assert inputs.vix is not None
    assert inputs.vix_source == "india_vix"
    assert inputs.reason_bits()
    result = service.run(datetime(2026, 1, 28), hydrate=False)
    assert result.label in {"Calm", "Elevated", "Stress"}
    again = service.run(datetime(2026, 1, 28), hydrate=False)
    assert again.label == result.label


def test_raw_candidate_vix_gates() -> None:
    cfg = RegimeCfg()
    assert raw_candidate(_inputs(vix=11.0), cfg) == "Calm"
    assert raw_candidate(_inputs(vix=16.0), cfg) == "Elevated"
    assert raw_candidate(_inputs(vix=21.0), cfg) == "Stress"


def _inputs(*, vix: float, as_of: datetime | None = None) -> RegimeInputs:
    return RegimeInputs(
        as_of=as_of or datetime(2026, 8, 11),
        vix=vix,
        nifty_close=24000,
        nifty_vs_sma50=1.0,
        ewma_vol_ann=0.10,
        kalman_trend=0.0002,
        kalman_trend_z=0.1,
        kalman_trend_ann_pct=5.0,
        vix_source="india_vix",
    )
