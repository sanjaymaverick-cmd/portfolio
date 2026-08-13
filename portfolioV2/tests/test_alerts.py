from __future__ import annotations

from datetime import UTC, datetime, timedelta

from meridian_v2.alerts.worker import AlertWorker
from meridian_v2.domain.models import PolicyKind
from meridian_v2.storage.schema import BookLegRow, Cooldown, OptionLegRow, RegimeState
from meridian_v2.storage.seed import seed_demo


def test_seed_and_reviews_open(session):
    seed_demo(session)
    session.flush()
    opened = AlertWorker(session).run_once(force=True)
    session.flush()
    assert opened["opened"] >= 1


def test_cooldown_suppresses_duplicate(session):
    seed_demo(session)
    session.add(
        Cooldown(
            policy_kind=PolicyKind.INVENTORY_HEDGE.value,
            symbol="GOLD",
            last_prompt_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    session.flush()
    worker = AlertWorker(session)
    first = worker.run_once(force=False)
    session.flush()
    # force=False should skip inventory GOLD due to cooldown (unless gamma+stress)
    second = worker.run_once(force=False)
    session.flush()
    assert second["opened"] <= first["opened"]


def test_stress_gamma_can_bypass(session):
    today = datetime.now(UTC).replace(tzinfo=None)
    session.add(RegimeState(label="Stress", reason="test", as_of=today))
    session.add(
        BookLegRow(
            leg_id="g1",
            symbol="GOLD",
            asset_class="commodity",
            lots=-3,
            multiplier=100,
            mark_inr=72000,
            contract_label="CONTINUOUS",
            delta=1.0,
            gamma=0.2,
            as_of=today.date(),
        )
    )
    session.add(
        OptionLegRow(
            leg_id="o1",
            symbol="GOLD",
            contract_label="P",
            lots=-3,
            multiplier=100,
            mark_inr=200,
            delta=0.4,
            gamma=0.2,
            vega_per_lot=50_000,
            greeks_as_of=today,
            stale=0,
        )
    )
    session.add(
        Cooldown(
            policy_kind=PolicyKind.VOL_HARVEST.value,
            symbol="GOLD",
            last_prompt_at=today - timedelta(hours=1),
        )
    )
    session.flush()
    result = AlertWorker(session).run_once(force=False)
    assert result["opened"] >= 1
