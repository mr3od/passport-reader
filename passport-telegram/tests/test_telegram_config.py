from __future__ import annotations

from passport_telegram.config import TelegramSettings
from pydantic import SecretStr


def test_allowed_chat_id_set_parses_csv():
    settings = TelegramSettings.model_construct(
        bot_token=SecretStr("token"),
        allowed_chat_ids="123, 456 ,789",
    )

    assert settings.allowed_chat_id_set == {123, 456, 789}


def test_admin_username_set_parses_handles():
    settings = TelegramSettings.model_construct(
        bot_token=SecretStr("token"),
        admin_usernames="@mr3od, admin2 ",
    )

    assert settings.admin_username_set == {"mr3od", "admin2"}


def test_admin_user_id_set_parses_csv():
    settings = TelegramSettings.model_construct(
        bot_token=SecretStr("token"),
        admin_user_ids="552002791, 743379791 ",
    )

    assert settings.admin_user_id_set == {552002791, 743379791}


def test_telegram_settings_do_not_expose_env_file_indirection():
    assert "core_env_file" not in TelegramSettings.model_fields
    assert "platform_env_file" not in TelegramSettings.model_fields
