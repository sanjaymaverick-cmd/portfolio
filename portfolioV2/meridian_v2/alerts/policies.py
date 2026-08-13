"""User-defined alert policies — local ack queue only."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_v2.domain.models import PolicyKind, SignalStatus
from meridian_v2.scoring.service import ScoringService
from meridian_v2.signals.service import SignalService
from meridian_v2.storage.schema import AlertPolicy, FxMark


def evaluate_policies(session: Session, *, regime: str) -> int:
    opened = 0
    signals = SignalService(session)
    scores = ScoringService(session).latest()
    usdinr = session.scalar(select(FxMark).where(FxMark.pair == "USDINR"))
    move = None
    if usdinr and usdinr.last and usdinr.prev_close:
        move = (usdinr.last - usdinr.prev_close) / usdinr.prev_close * 100
    for policy in session.scalars(select(AlertPolicy).where(AlertPolicy.enabled == 1)):
        fired = False
        why = policy.notes or policy.name
        symbol = policy.symbol if policy.symbol != "*" else "DESK"
        if policy.kind == "score_below":
            targets = scores.items() if policy.symbol == "*" else [(policy.symbol, scores.get(policy.symbol))]
            for sym, row in targets:
                if row and row.composite is not None and row.composite <= policy.threshold:
                    fired = True
                    symbol = sym
                    why = f"Score {row.composite:.1f} ≤ {policy.threshold:.1f} ({regime})"
                    break
        elif policy.kind == "usdinr_move" and move is not None:
            fired = abs(move) >= policy.threshold
            symbol = "USDINR"
            why = f"USDINR move {move:+.2f}% vs policy {policy.threshold:.2f}%"
        elif policy.kind == "regime_is":
            fired = regime.lower() == (policy.notes or "stress").lower() or regime == "Stress"
            why = f"Regime is {regime}"
        if not fired:
            continue
        signals.enqueue(
            policy_kind=PolicyKind.SIGNAL.value,
            symbol=symbol,
            copy_review=f"POLICY REVIEW — not an order. {why}. Review the desk?",
            reason=why,
            regime=regime,
            rule_name=f"policy:{policy.kind}",
            payload={"policy_id": policy.id, "name": policy.name},
            status=SignalStatus.PENDING.value,
        )
        opened += 1
    return opened
