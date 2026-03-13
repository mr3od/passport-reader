from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PASSPORT_PLATFORM_",
        env_file=".env",
        extra="ignore",
    )

    db_path: Path = Path("data/platform.sqlite3")
    artifact_store_backend: Literal["local"] = "local"
    artifacts_dir: Path = Path("data/artifacts")
    log_level: str = "INFO"
