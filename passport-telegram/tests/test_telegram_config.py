from __future__ import annotations

from passport_telegram.config import TelegramSettings
from pydantic import SecretStr


def test_agency_bot_settings_keep_batch_and_logging_defaults():
    settings = TelegramSettings.model_construct(
        bot_token=SecretStr("token"),
    )

    assert settings.album_collection_window_seconds == 1.5
    assert settings.max_images_per_batch == 10
    assert settings.log_level == "INFO"


def test_telegram_settings_do_not_expose_env_file_indirection():
    assert "core_env_file" not in TelegramSettings.model_fields
    assert "platform_env_file" not in TelegramSettings.model_fields


def test_telegram_settings_do_not_expose_removed_chat_or_admin_fields():
    assert "allowed_chat_ids" not in TelegramSettings.model_fields
    assert "admin_user_ids" not in TelegramSettings.model_fields
    assert "admin_usernames" not in TelegramSettings.model_fields
