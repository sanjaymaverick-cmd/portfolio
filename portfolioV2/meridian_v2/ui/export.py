from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.alerts.worker import current_regime
from meridian_v2.config import get_settings
from meridian_v2.journal.service import JournalService
from meridian_v2.risk.stress import nifty_down_scenario
from meridian_v2.scoring.service import ScoringService
from meridian_v2.signals.service import SignalService
from meridian_v2.storage.schema import WatchItem


def research_notebook(session: Session) -> str:
    settings = get_settings()
    regime = current_regime(session, settings)
    scores = ScoringService(session).latest()
    pending = SignalService(session).pending()
    stress = nifty_down_scenario(session)
    lines = [
        f"# MERIDIAN V2 desk brief · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        "Advisory only. Not an order. Isolated from v1.",
        "",
        f"## Regime",
        f"{regime.value}",
        "",
        "## Watch (active)",
    ]
    for item in session.scalars(select(WatchItem).where(WatchItem.status == "active").order_by(WatchItem.symbol)):
        score = scores.get(item.symbol)
        comp = f"{score.composite:.1f}" if score and score.composite is not None else "—"
        lines.append(f"- {item.symbol} ({item.asset_class}) stance={item.stance or '—'} score={comp} · {item.notes}")
    lines += ["", "## Open reviews"]
    if not pending:
        lines.append("- none")
    for ev in pending:
        lines.append(f"- [{ev.policy_kind}] {ev.symbol}: {ev.copy_review}")
    lines += ["", "## Journal (latest 8)"]
    for row in JournalService(session).post_mortems()[:8]:
        intent = row["intent"]
        lines.append(
            f"- #{intent.id} {intent.policy_kind} {intent.side} {intent.lots} {intent.symbol} "
            f"then={row['regime_then']} now={row['regime_now']}"
        )
    lines += ["", "## Stress stub", stress.copy, ""]
    return "\n".join(lines)
