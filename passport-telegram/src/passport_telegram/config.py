from __future__ import annotations

from pydantic import SecretStr
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
