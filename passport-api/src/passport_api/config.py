from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PASSPORT_API_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    platform_env_file: Path = Path("../passport-platform/.env")

    @property
    def platform_root_dir(self) -> Path:
        return self.platform_env_file.expanduser().resolve().parent
