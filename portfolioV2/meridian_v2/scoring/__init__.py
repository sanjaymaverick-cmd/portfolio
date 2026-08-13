"""Optional factor-concept stubs — v2 does not import v1 scoring."""

from meridian_v2.scoring.service import ScoringService, tape_score

score_from_tape = tape_score

__all__ = ["ScoringService", "score_from_tape", "tape_score"]

