from __future__ import annotations

from datetime import date
from pathlib import Path

from meridian_v2.ingestion.csv_import import import_watch_csv
from meridian_v2.journal.service import JournalService
from meridian_v2.risk.stress import nifty_down_scenario
from meridian_v2.signals.backtest import run_paper_backtest
from meridian_v2.signals.engines import breakout_volume, cross_asset_overlay, mean_reversion_bands
from meridian_v2.storage.schema import PriceCache
from meridian_v2.watchlist.service import WatchlistService


def test_mean_reversion_and_breakout_and_cross_asset():
    mr = mean_reversion_bands("TCS", last=100, mid=110, high20=120, low20=100, regime="Calm")
    assert mr is not None
    assert mr.rule_name == "mean_reversion_bands"
    br = breakout_volume("TCS", last=121, high20=120, volume=2000, prev_volume=1000, regime="Calm")
    assert br is not None
    assert "Breakout" in br.reason
    xa = cross_asset_overlay(
        "RELIANCE", "equity", "Elevated", usdinr_move_pct=1.4, commodity_stress=False
    )
    assert xa is not None
    assert xa.rule_name == "cross_asset_overlay"


def test_catalysts_and_stance(session):
    svc = WatchlistService(session)
    item = svc.add("INFY", "equity", "research", stance="wait", sector="it")
    session.flush()
    svc.add_catalyst(item.id, "results", event_date=date.today(), notes="Q1")
    session.flush()
    cats = svc.catalysts(item.id)
    assert cats[0].kind == "results"
    assert item.stance == "wait"


def test_desk_snapshot_on_intent(session):
    svc = JournalService(session)
    intent = svc.add_intent(policy_kind="signal", symbol="GOLD", side="buy", lots=1, reason="note")
    session.flush()
    assert "regime" in intent.desk_snapshot_json
    svc.capture_outcome(intent.id)
    session.flush()
    rows = svc.post_mortems()
    assert rows[0]["before"]["symbol"] == "GOLD"


def test_paper_backtest_hook(session):
    from datetime import UTC, datetime

    session.add(
        PriceCache(
            symbol="TCS",
            contract_label="CONTINUOUS",
            last=100,
            prev_close=98,
            as_of=datetime.now(UTC).replace(tzinfo=None),
            high20=99,
            low20=90,
            volume=2000,
            prev_volume=1000,
        )
    )
    session.flush()
    from sqlalchemy import select

    price = session.scalar(select(PriceCache).where(PriceCache.symbol == "TCS"))
    run = run_paper_backtest(session, price, asset_class="equity")
    assert run.bars == 12
    assert "PAPER BACKTEST" in run.report


def test_stress_stub_copy(session):
    note = nifty_down_scenario(session)
    assert "not an order" in note.copy.lower()
    assert "STRESS NOTE" in note.copy


def test_csv_watch_import(session, tmp_path: Path):
    path = tmp_path / "watch.csv"
    path.write_text("symbol,asset_class,notes,stance,sector\nWIPRO,equity,research,consider,it\n", encoding="utf-8")
    accepted, rejected = import_watch_csv(session, path)
    session.flush()
    assert accepted == 1
    assert rejected == 0
    assert WatchlistService(session).active()[0].symbol == "WIPRO"
