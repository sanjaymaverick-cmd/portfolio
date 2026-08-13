from __future__ import annotations

import pytest

from meridian_v2.domain.copy import assert_review_copy, fx_review_copy


def test_fx_copy_is_a_question():
    text = fx_review_copy(
        pair="USDINR",
        move_pct=1.2,
        regime="Elevated",
        why="Open GOLD hedge legs sit against the rupee move.",
    )
    assert "REVIEW" in text
    assert "not an order" in text.lower()
    assert "?" in text
    assert "execute" not in text.lower()
    assert "you should hedge" not in text.lower()


def test_forbidden_language_rejected():
    with pytest.raises(ValueError):
        assert_review_copy("You should hedge GOLD now")
    with pytest.raises(ValueError):
        assert_review_copy("Execute the futures clip")
