from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminBotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PASSPORT_ADMIN_BOT_",
        env_file=".env",
        extra="ignore",
    )

    bot_token: SecretStr
    admin_user_ids: str = ""
    admin_usernames: str = ""
    log_level: str = "INFO"

    @property
    def admin_username_set(self) -> set[str]:
        raw_values = [item.strip().lstrip("@") for item in self.admin_usernames.split(",")]
        return {item.lower() for item in raw_values if item}

    @property
    def admin_user_id_set(self) -> set[int]:
        raw_values = [item.strip() for item in self.admin_user_ids.split(",") if item.strip()]
        return {int(item) for item in raw_values}
