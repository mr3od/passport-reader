from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr
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
    log_level: str = "INFO"
    github_release_read_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("PASSPORT_GITHUB_RELEASE_READ_TOKEN"),
    )
    github_repo: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PASSPORT_GITHUB_REPO"),
    )
