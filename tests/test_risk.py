from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from meridian.domain.models import MappedRow
from meridian.risk.math import corr_beta, rsi, seed_ewma, shrink_beta, sma
from meridian.risk.service import BOOK, RiskService
from meridian.scoring.technical import score_technical
from meridian.storage.repositories import AccountRepo, HoldingRepo
from meridian.storage.schema import Base, PriceBar


def test_corr_beta_known() -> None:
    market = [0.01, -0.01, 0.02, 0.00, -0.015, 0.01, 0.005]
    twin = list(market)
    rho, beta = corr_beta(twin, market)
    assert rho is not None and abs(rho - 1.0) < 1e-9
    assert beta is not None and abs(beta - 1.0) < 1e-9
    double = [2 * x for x in market]
    rho2, beta2 = corr_beta(double, market)
    assert rho2 is not None and abs(rho2 - 1.0) < 1e-9
    assert beta2 is not None and abs(beta2 - 2.0) < 1e-9


def test_ewma_moves_toward_new_obs() -> None:
    state = seed_ewma([0.01] * 30, [0.01] * 30, 0.94)
    before = state.beta
    for _ in range(8):
        state.update(0.04, 0.01)
    assert before is not None and state.beta is not None
    assert state.beta > before


def test_seed_ewma_preserves_zero_beta() -> None:
    # Asset uncorrelated with market over the warmup → genuine beta 0.0.
    # Orthogonal 4-cycles give cov == 0 exactly while both variances are > 0.
    market = [0.02, -0.02, 0.02, -0.02] * 5
    asset = [0.02, 0.02, -0.02, -0.02] * 5
    rho, beta = corr_beta(asset, market)
    assert beta is not None and abs(beta) < 1e-12
    state = seed_ewma(asset, market, 0.94)
    # Must seed near zero, not snap to 1.0 (the old `beta or 1.0` bug).
    assert state.beta is not None and abs(state.beta) < 1e-9


def test_shrink_and_sma_rsi() -> None:
    assert abs((shrink_beta(2.0, 0.15) or 0) - 1.85) < 1e-9
    closes = [100 + i for i in range(30)]
    assert sma(closes, 20) == sum(closes[-20:]) / 20
    value = rsi(closes, 14)
    assert value is not None and value > 70


def test_technical_score_range() -> None:
    score, parts = score_technical(
        last=120,
        sma20=118,
        sma50=110,
        sma200=100,
        rsi=55,
        rs_nifty=0.08,
        volume_ratio=1.2,
    )
    assert score is not None and Decimal("6") <= score <= Decimal("9.5")
    assert parts["trend"] is not None


def test_risk_service_on_synthetic_book(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}", future=True)
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine, future=True)()
    account = AccountRepo(session).create("Core", "zerodha")
    HoldingRepo(session).upsert(
        account,
        MappedRow(
            symbol="AAA",
            exchange="NSE",
            quantity=Decimal("10"),
            avg_cost=Decimal("100"),
            last_price=Decimal("120"),
        ),
    )
    start = datetime(2025, 1, 2)
    nifty = 20000.0
    price = 100.0
    for day in range(90):
        nifty *= 1.001
        price *= 1.002
        when = start + timedelta(days=day)
        session.add(
            PriceBar(
                yahoo="AAA.NS",
                bar_date=when,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1000,
            )
        )
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
    session.commit()
    result = RiskService(session).compute(force=True)
    assert result.marked == 1
    snap = RiskService(session).risk.get("AAA")
    assert snap is not None and snap.beta_ols is not None
    book = RiskService(session).risk.get(BOOK)
    assert book is not None
