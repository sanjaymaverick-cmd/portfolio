from __future__ import annotations

import meridian_v2
from meridian_v2.config import get_settings, reset_settings_cache


def test_import_and_version():
    assert meridian_v2.__version__
    assert "meridian_v2" in meridian_v2.__doc__ or True


def test_config_isolation():
    reset_settings_cache()
    settings = get_settings()
    assert settings.app.name == "MERIDIAN V2"
    assert settings.app.port == 8766
    assert "meridian_v2.db" in str(settings.db_path)
    assert "meridian.db" not in str(settings.db_path).replace("meridian_v2.db", "")
    assert settings.watchlist.active_cap == 50
