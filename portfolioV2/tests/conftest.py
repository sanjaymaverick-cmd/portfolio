from __future__ import annotations

import pytest

from meridian_v2.config import reset_settings_cache
from meridian_v2.storage.db import get_session, init_db, reset_engine


@pytest.fixture
def session(tmp_path, monkeypatch):
    db = tmp_path / "meridian_v2_test.db"
    monkeypatch.setenv("MERIDIAN_V2_TEST_DB", str(db))
    reset_settings_cache()
    reset_engine()
    init_db()
    sess = get_session()
    try:
        yield sess
        sess.rollback()
    finally:
        sess.close()
        reset_engine()
        reset_settings_cache()
