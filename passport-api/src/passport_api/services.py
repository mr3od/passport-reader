from __future__ import annotations

from dataclasses import dataclass, field

from passport_platform import (
    AuthService,
    ProcessingService,
    RecordsService,
    UserService,
    build_platform_runtime,
    build_processing_runtime,
)

from passport_api.config import ApiSettings


@dataclass(slots=True)
class ApiServices:
    auth: AuthService
    records: RecordsService
    users: UserService
    processing: ProcessingService | None = field(default=None)


def build_services(settings: ApiSettings) -> ApiServices:
    platform_runtime = build_platform_runtime(
        platform_env_file=settings.platform_env_file,
        platform_root_dir=settings.platform_root_dir,
    )
    processing_runtime = build_processing_runtime(
        platform_runtime=platform_runtime,
        core_env_file=getattr(settings, "core_env_file", None),
        core_root_dir=getattr(settings, "core_root_dir", None),
    )
    auth = platform_runtime.auth
    records = platform_runtime.records
    users = platform_runtime.users
    processing = processing_runtime.processing
    return ApiServices(auth=auth, records=records, users=users, processing=processing)
