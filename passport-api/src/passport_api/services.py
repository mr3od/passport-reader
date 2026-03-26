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


@dataclass(slots=True)
class ApiServices:
    auth: AuthService
    records: RecordsService
    users: UserService
    processing: ProcessingService | None = field(default=None)


def build_services() -> ApiServices:
    """Build the shared API service container from the root workspace environment."""
    platform_runtime = build_platform_runtime()
    processing_runtime = build_processing_runtime(platform_runtime=platform_runtime)
    auth = platform_runtime.auth
    records = platform_runtime.records
    users = platform_runtime.users
    processing = processing_runtime.processing
    return ApiServices(auth=auth, records=records, users=users, processing=processing)
