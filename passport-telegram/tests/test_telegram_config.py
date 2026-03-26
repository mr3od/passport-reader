from __future__ import annotations

from pathlib import Path

from passport_telegram.config import TelegramSettings


def test_allowed_chat_id_set_parses_csv():
    settings = TelegramSettings(
        _env_file=None,
        bot_token="token",
        allowed_chat_ids="123, 456 ,789",
    )

    assert settings.allowed_chat_id_set == {123, 456, 789}


def test_admin_username_set_parses_handles():
    settings = TelegramSettings(
        _env_file=None,
        bot_token="token",
        admin_usernames="@mr3od, admin2 ",
    )

    assert settings.admin_username_set == {"mr3od", "admin2"}


def test_admin_user_id_set_parses_csv():
    settings = TelegramSettings(
        _env_file=None,
        bot_token="token",
        admin_user_ids="552002791, 743379791 ",
    )

    assert settings.admin_user_id_set == {552002791, 743379791}


def test_core_root_dir_resolves_from_env_file():
    settings = TelegramSettings(
        _env_file=None,
        bot_token="token",
        core_env_file=".env",
    )

    assert settings.core_root_dir == Path(".env").resolve().parent


def test_platform_root_dir_resolves_from_env_file():
    settings = TelegramSettings(
        _env_file=None,
        bot_token="token",
        platform_env_file=".env",
    )

    assert settings.platform_root_dir == Path(".env").resolve().parent
