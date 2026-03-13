from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from passport_platform import (
    AuthService,
    Database,
    PlatformSettings,
    RecordsService,
    UserService,
)
from passport_platform.repositories import (
    AuthTokensRepository,
    RecordsRepository,
    UsersRepository,
)

from passport_api.config import ApiSettings


@dataclass(slots=True)
class ApiServices:
    auth: AuthService
    records: RecordsService
    users: UserService


def build_services(settings: ApiSettings) -> ApiServices:
    platform_settings = PlatformSettings(_env_file=settings.platform_env_file)
    platform_settings.db_path = _resolve_path(settings.platform_root_dir, platform_settings.db_path)
    db = Database(platform_settings.db_path)
    db.initialize()
    users = UserService(UsersRepository(db))
    auth = AuthService(AuthTokensRepository(db), users)
    records = RecordsService(RecordsRepository(db))
    return ApiServices(
        auth=auth,
        records=records,
        users=users,
    )


def _resolve_path(root: str | Path, value: Path) -> Path:
    root_path = Path(root)
    if value.is_absolute():
        return value
    return (root_path / value).resolve()
