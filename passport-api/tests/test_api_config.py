from __future__ import annotations

from pathlib import Path

from passport_api.config import ApiSettings


def test_core_root_dir_defaults_to_workspace_root_env():
    settings = ApiSettings(
        _env_file=None,
        core_env_file=".env",
    )

    assert settings.core_root_dir == Path(".env").resolve().parent


def test_platform_root_dir_defaults_to_workspace_root_env():
    settings = ApiSettings(
        _env_file=None,
        platform_env_file=".env",
    )

    assert settings.platform_root_dir == Path(".env").resolve().parent
