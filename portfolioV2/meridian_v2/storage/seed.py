from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meridian_v2.storage.schema import (
    AlertPolicy,
    BookLegRow,
    FxMark,
    HedgeLegRow,
    McxContract,
    NewsStub,
    OptionLegRow,
    PriceCache,
    RegimeState,
    WatchCatalyst,
    WatchItem,
)


def seed_demo(session: Session, *, reset: bool = False) -> int:
    if reset:
        for model in (
            WatchCatalyst,
            AlertPolicy,
            NewsStub,
            WatchItem,
            McxContract,
            PriceCache,
            BookLegRow,
            HedgeLegRow,
            OptionLegRow,
            FxMark,
            RegimeState,
        ):
            for row in session.scalars(select(model)):
                session.delete(row)
        session.flush()
    elif session.scalar(select(func.count()).select_from(WatchItem)):
        return 0

    now = datetime.now(UTC).replace(tzinfo=None)
    today = date.today()
    roll = today + timedelta(days=18)

    watch = [
        ("RELIANCE", "equity", "Core holding research", "wait", "energy"),
        ("TCS", "equity", "IT quality", "consider", "it"),
        ("HDFCBANK", "equity", "Financials", "wait", "banks"),
        ("GOLD", "commodity", "MCX inventory", "consider", "metals"),
        ("SILVER", "commodity", "MCX satellite", "wait", "metals"),
        ("CRUDEOIL", "commodity", "Energy book", "avoid", "energy"),
        ("USDINR", "fx", "Macro overlay", "wait", "macro"),
    ]
    for symbol, asset, notes, stance, sector in watch:
        session.add(
            WatchItem(
                symbol=symbol,
                asset_class=asset,
                status="active",
                notes=notes,
                stance=stance,
                sector=sector,
                created_at=now,
                updated_at=now,
            )
        )

    contracts = [
        ("GOLD", "GOLD26APR", "GOLD26JUN", 100.0, "MCX gold — continuous vs contract labelled"),
        ("SILVER", "SILVER26MAY", "SILVER26JUL", 30.0, "MCX silver"),
        ("CRUDEOIL", "CRUDEOIL26MAY", "CRUDEOIL26JUN", 100.0, "MCX crude"),
        ("COPPER", "COPPER26MAY", "COPPER26JUN", 2500.0, "MCX copper"),
        ("NATURALGAS", "NATGAS26MAY", "NATGAS26JUN", 1250.0, "MCX natgas"),
    ]
    for key, near, nxt, mult, notes in contracts:
        session.add(
            McxContract(
                symbol_key=key,
                near_label=near,
                next_label=nxt,
                roll_date=roll,
                multiplier=mult,
                series_kind="CONTINUOUS",
                notes=notes,
            )
        )
        session.add(
            PriceCache(
                symbol=key,
                contract_label="CONTINUOUS",
                series_kind="CONTINUOUS",
                last={"GOLD": 72000.0, "SILVER": 82000.0, "CRUDEOIL": 6200.0, "COPPER": 850.0, "NATURALGAS": 280.0}[
                    key
                ],
                prev_close={"GOLD": 71500.0, "SILVER": 81200.0, "CRUDEOIL": 6100.0, "COPPER": 848.0, "NATURALGAS": 275.0}[
                    key
                ],
                as_of=now,
                quality="seed",
                source="demo",
                sma20={"GOLD": 71000.0, "SILVER": 80000.0, "CRUDEOIL": 6400.0, "COPPER": 840.0, "NATURALGAS": 270.0}[key],
                sma50={"GOLD": 70000.0, "SILVER": 79000.0, "CRUDEOIL": 6500.0, "COPPER": 830.0, "NATURALGAS": 265.0}[key],
                weekly_last={"GOLD": 71800.0, "SILVER": 81800.0, "CRUDEOIL": 6150.0, "COPPER": 848.0, "NATURALGAS": 278.0}[
                    key
                ],
                weekly_sma={"GOLD": 70500.0, "SILVER": 79500.0, "CRUDEOIL": 6450.0, "COPPER": 835.0, "NATURALGAS": 268.0}[
                    key
                ],
                high20={"GOLD": 72500.0, "SILVER": 83000.0, "CRUDEOIL": 6600.0, "COPPER": 860.0, "NATURALGAS": 290.0}[key],
                low20={"GOLD": 69800.0, "SILVER": 78000.0, "CRUDEOIL": 6000.0, "COPPER": 820.0, "NATURALGAS": 255.0}[key],
                volume=12000,
                prev_volume=8000,
            )
        )
        session.add(
            PriceCache(
                symbol=key,
                contract_label=near,
                series_kind="CONTRACT",
                last={"GOLD": 72120.0, "SILVER": 82110.0, "CRUDEOIL": 6215.0, "COPPER": 852.0, "NATURALGAS": 281.0}[
                    key
                ],
                prev_close=None,
                as_of=now,
                quality="seed",
                source="demo",
            )
        )

    session.add(
        BookLegRow(
            leg_id="gold-inv-1",
            symbol="GOLD",
            asset_class="commodity",
            lots=2.0,
            multiplier=100.0,
            mark_inr=72000.0,
            contract_label="CONTINUOUS",
            delta=1.0,
            gamma=0.0,
            as_of=today,
        )
    )
    session.add(
        HedgeLegRow(
            leg_id="gold-fut-1",
            symbol="GOLD",
            asset_class="commodity",
            lots=0.0,
            multiplier=100.0,
            mark_inr=72000.0,
            contract_label="GOLD26APR",
            delta=1.0,
            gamma=0.0,
            as_of=today,
        )
    )
    session.add(
        OptionLegRow(
            leg_id="gold-call-atm",
            symbol="GOLD",
            contract_label="GOLD26MAY 72000 CE",
            lots=4.0,
            multiplier=100.0,
            mark_inr=315.0,
            delta=0.50,
            gamma=0.08,
            vega_per_lot=60_000.0,
            theta_per_lot=-1200.0,
            iv=0.16,
            greeks_as_of=now,
            stale=0,
        )
    )

    for symbol, last, prev, sma in (
        ("RELIANCE", 1390.0, 1410.0, 1425.0),
        ("TCS", 3920.0, 3880.0, 3850.0),
        ("HDFCBANK", 1650.0, 1640.0, 1660.0),
    ):
        session.add(
            PriceCache(
                symbol=symbol,
                contract_label="CONTINUOUS",
                series_kind="CONTINUOUS",
                last=last,
                prev_close=prev,
                as_of=now,
                quality="seed",
                source="demo",
                sma20=sma,
                sma50=sma * 0.98,
                weekly_last=last,
                weekly_sma=sma,
                high20=max(last, prev, sma) * 1.02,
                low20=min(last, prev, sma) * 0.97,
                volume=2_000_000,
                prev_volume=1_400_000,
            )
        )

    session.add(FxMark(pair="USDINR", last=83.72, prev_close=82.90, as_of=now, quality="seed", source="demo"))
    session.add(FxMark(pair="EURUSD", last=1.086, prev_close=1.084, as_of=now, quality="seed", source="demo"))
    session.add(FxMark(pair="USDJPY", last=154.2, prev_close=153.8, as_of=now, quality="seed", source="demo"))
    session.add(
        RegimeState(
            label="Elevated",
            reason="Seeded sensors: USDINR +1.0% and mixed commodity tape.",
            as_of=now,
        )
    )
    session.add(NewsStub(symbol="RELIANCE", headline="Results week — energy names in focus", tone=-0.2, as_of=now))
    session.add(NewsStub(symbol="TCS", headline="Deal pipeline commentary constructive", tone=0.3, as_of=now))
    session.flush()
    rel = session.scalar(select(WatchItem).where(WatchItem.symbol == "RELIANCE"))
    gold = session.scalar(select(WatchItem).where(WatchItem.symbol == "GOLD"))
    if rel:
        session.add(
            WatchCatalyst(
                watch_id=rel.id,
                kind="results",
                event_date=today + timedelta(days=9),
                notes="Results date — gate new risk",
            )
        )
    if gold:
        session.add(
            WatchCatalyst(
                watch_id=gold.id,
                kind="level",
                event_date=None,
                level=70000,
                notes="GOLD technical shelf",
            )
        )
    session.add(
        AlertPolicy(
            name="Score drop",
            kind="score_below",
            symbol="*",
            threshold=4.0,
            enabled=1,
            notes="Surface names whose composite has slipped",
        )
    )
    session.add(
        AlertPolicy(
            name="USDINR jump",
            kind="usdinr_move",
            symbol="USDINR",
            threshold=1.0,
            enabled=1,
            notes="Macro overlay",
        )
    )
    session.flush()
    return 7
