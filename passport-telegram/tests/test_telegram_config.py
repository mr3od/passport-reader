from __future__ import annotations

from passport_telegram.config import TelegramSettings
from pydantic import SecretStr


def test_agency_bot_settings_keep_batch_and_logging_defaults():
    settings = TelegramSettings.model_construct(
        bot_token=SecretStr("token"),
    )

    assert settings.album_collection_window_seconds == 1.5
    assert settings.max_images_per_batch == 10
    assert settings.max_inflight_upload_batches == 20
    assert settings.inflight_acquire_timeout_seconds == 3.0
    assert settings.log_level == "INFO"


def test_telegram_settings_do_not_expose_env_file_indirection():
    assert "core_env_file" not in TelegramSettings.model_fields
    assert "platform_env_file" not in TelegramSettings.model_fields


def test_telegram_settings_do_not_expose_removed_chat_or_admin_fields():
    assert "allowed_chat_ids" not in TelegramSettings.model_fields
    assert "admin_user_ids" not in TelegramSettings.model_fields
    assert "admin_usernames" not in TelegramSettings.model_fields


def test_github_token_loaded_from_env(monkeypatch):
    monkeypatch.setenv("PASSPORT_TELEGRAM_BOT_TOKEN", "dummy")
    monkeypatch.setenv("PASSPORT_GITHUB_RELEASE_READ_TOKEN", "ghp_test")
    monkeypatch.setenv("PASSPORT_GITHUB_REPO", "owner/repo")
    s = TelegramSettings()
    assert s.github_release_read_token.get_secret_value() == "ghp_test"
    assert s.github_repo == "owner/repo"


def test_github_fields_default_to_none(monkeypatch):
    monkeypatch.setenv("PASSPORT_TELEGRAM_BOT_TOKEN", "dummy")
    monkeypatch.delenv("PASSPORT_GITHUB_RELEASE_READ_TOKEN", raising=False)
    monkeypatch.delenv("PASSPORT_GITHUB_REPO", raising=False)
    s = TelegramSettings()
    assert s.github_release_read_token is None
    assert s.github_repo is None


def test_github_token_is_secret_str(monkeypatch):
    monkeypatch.setenv("PASSPORT_TELEGRAM_BOT_TOKEN", "dummy")
    monkeypatch.setenv("PASSPORT_GITHUB_RELEASE_READ_TOKEN", "ghp_secret")
    s = TelegramSettings()
    assert "ghp_secret" not in str(s)  # SecretStr hides value in repr
    assert s.github_release_read_token.get_secret_value() == "ghp_secret"
