from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PASSPORT_TELEGRAM_",
        env_file=".env",
        extra="ignore",
    )

    bot_token: SecretStr
    album_collection_window_seconds: float = 1.5
    max_images_per_batch: int = 10
    max_inflight_upload_batches: int = Field(default=20, ge=1)
    inflight_acquire_timeout_seconds: float = Field(default=3.0, gt=0)
    log_level: str = "INFO"
    # These two fields intentionally bypass the PASSPORT_TELEGRAM_ prefix so that
    # the same GitHub credentials can be shared across multiple adapters without
    # duplicating per-adapter env vars.
    github_release_read_token: SecretStr | None = Field(
        default=None,
        validation_alias="PASSPORT_GITHUB_RELEASE_READ_TOKEN",
    )
    github_repo: str | None = Field(
        default=None,
        validation_alias="PASSPORT_GITHUB_REPO",
    )
