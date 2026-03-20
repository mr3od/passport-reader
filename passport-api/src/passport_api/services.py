from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from passport_platform import (
    AuthService,
    Database,
    PlatformSettings,
    ProcessingService,
    QuotaService,
    RecordsService,
    UploadService,
    UserService,
    build_processing_service,
)
from passport_platform.repositories import (
    AuthTokensRepository,
    RecordsRepository,
    UsageRepository,
    UploadsRepository,
    UsersRepository,
)

from passport_api.config import ApiSettings


@dataclass(slots=True)
class ApiServices:
    auth: AuthService
    records: RecordsService
    users: UserService
    processing: ProcessingService | None = field(default=None)


def build_services(settings: ApiSettings) -> ApiServices:
    platform_settings = PlatformSettings(_env_file=settings.platform_env_file)
    platform_settings.db_path = _resolve(settings.platform_root_dir, platform_settings.db_path)
    platform_settings.artifacts_dir = _resolve(
        settings.platform_root_dir, platform_settings.artifacts_dir
    )
    db = Database(platform_settings.db_path)
    db.initialize()
    users = UserService(UsersRepository(db))
    auth = AuthService(AuthTokensRepository(db), users)
    records = RecordsService(RecordsRepository(db))
    core_env_file = getattr(settings, "core_env_file", None)
    core_root_dir = getattr(settings, "core_root_dir", None)
    processing = (
        build_processing_service(
            core_env_file=core_env_file.expanduser().resolve(),
            core_root_dir=core_root_dir,
            platform_settings=platform_settings,
            db=db,
        )
        if core_env_file is not None and core_root_dir is not None
        else None
    )
    return ApiServices(auth=auth, records=records, users=users, processing=processing)


def _resolve(root: str | Path, value: Path) -> Path:
    root_path = Path(root)
    if value.is_absolute():
        return value
    return (root_path / value).resolve()
