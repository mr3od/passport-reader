from __future__ import annotations

from passport_api.config import ApiSettings


def test_api_settings_do_not_expose_env_file_indirection():
    assert "core_env_file" not in ApiSettings.model_fields
    assert "platform_env_file" not in ApiSettings.model_fields
