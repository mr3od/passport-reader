from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PASSPORT_TELEGRAM_",
        env_file=".env",
        extra="ignore",
    )

    bot_token: SecretStr
    core_env_file: Path = Path("../passport-core/.env")
    platform_env_file: Path = Path("../passport-platform/.env")
    allowed_chat_ids: str = ""
    admin_user_ids: str = "552002791,743379791"
    admin_usernames: str = "mr3od,naaokun"
    album_collection_window_seconds: float = 1.5
    max_images_per_batch: int = 10
    log_level: str = "INFO"

    @property
    def core_root_dir(self) -> Path:
        return self.core_env_file.expanduser().resolve().parent

    @property
    def platform_root_dir(self) -> Path:
        return self.platform_env_file.expanduser().resolve().parent

    @property
    def allowed_chat_id_set(self) -> set[int]:
        raw_values = [item.strip() for item in self.allowed_chat_ids.split(",") if item.strip()]
        return {int(item) for item in raw_values}

    @property
    def admin_username_set(self) -> set[str]:
        raw_values = [item.strip().lstrip("@") for item in self.admin_usernames.split(",")]
        return {item.lower() for item in raw_values if item}

    @property
    def admin_user_id_set(self) -> set[int]:
        raw_values = [item.strip() for item in self.admin_user_ids.split(",") if item.strip()]
        return {int(item) for item in raw_values}
