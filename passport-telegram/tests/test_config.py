from __future__ import annotations

from passport_telegram.config import TelegramSettings


def test_allowed_chat_id_set_parses_csv():
    settings = TelegramSettings(
        _env_file=None,
        bot_token="token",
        allowed_chat_ids="123, 456 ,789",
    )

    assert settings.allowed_chat_id_set == {123, 456, 789}


def test_core_root_dir_resolves_from_env_file():
    settings = TelegramSettings(
        _env_file=None,
        bot_token="token",
        core_env_file="../passport-core/.env",
    )

    assert settings.core_root_dir.name == "passport-core"


def test_platform_root_dir_resolves_from_env_file():
    settings = TelegramSettings(
        _env_file=None,
        bot_token="token",
        platform_env_file="../passport-platform/.env",
    )

    assert settings.platform_root_dir.name == "passport-platform"
