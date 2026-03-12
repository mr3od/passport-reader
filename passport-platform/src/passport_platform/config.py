from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PASSPORT_PLATFORM_",
        env_file=".env",
        extra="ignore",
    )

    db_path: Path = Path("data/platform.sqlite3")
    log_level: str = "INFO"
