from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from passport_platform.config import PlatformSettings
from passport_platform.db import Database
from passport_platform.repositories.auth_tokens import AuthTokensRepository
from passport_platform.repositories.records import RecordsRepository
from passport_platform.repositories.reporting import ReportingRepository
from passport_platform.repositories.uploads import UploadsRepository
from passport_platform.repositories.usage import UsageRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.services.auth import AuthService
from passport_platform.services.processing import ProcessingService
from passport_platform.services.quotas import QuotaService
from passport_platform.services.records import RecordsService
from passport_platform.services.reporting import ReportingService
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService
from passport_platform.storage import LocalArtifactStore

log = logging.getLogger(__name__)


@dataclass(slots=True)
class PlatformRuntime:
    """Shared platform services and state for transport adapters."""

    settings: PlatformSettings
    db: Database
    artifacts: LocalArtifactStore
    users: UserService
    auth: AuthService
    quotas: QuotaService
    uploads: UploadService
    records: RecordsService
    reporting: ReportingService


@dataclass(slots=True)
class ProcessingRuntime:
    """Platform runtime plus the optional OCR processing service."""

    platform: PlatformRuntime
    processing: ProcessingService | None


def build_platform_runtime(
    *,
    platform_env_file: Path,
    platform_root_dir: Path,
) -> PlatformRuntime:
    """Build the shared platform runtime used by transport adapters."""
    resolved_platform_env_file = platform_env_file.expanduser().resolve()
    resolved_platform_root_dir = platform_root_dir.expanduser().resolve()
    settings = cast(Any, PlatformSettings)(_env_file=resolved_platform_env_file)
    settings.db_path = _resolve(resolved_platform_root_dir, settings.db_path)
    settings.artifacts_dir = _resolve(resolved_platform_root_dir, settings.artifacts_dir)

    db = Database(settings.db_path)
    db.initialize()
    return _build_platform_runtime(settings=settings, db=db)


def build_processing_runtime(
    *,
    platform_runtime: PlatformRuntime,
    core_env_file: Path | None,
    core_root_dir: Path | None,
) -> ProcessingRuntime:
    """Build the OCR processing runtime on top of an existing platform runtime."""
    if core_env_file is None:
        return ProcessingRuntime(platform=platform_runtime, processing=None)

    resolved_core_env_file = core_env_file.expanduser().resolve()
    resolved_core_root_dir = (
        core_root_dir.expanduser().resolve()
        if core_root_dir is not None
        else resolved_core_env_file.parent
    )

    if not resolved_core_env_file.exists():
        log.info(
            "passport-core .env not found at %s — OCR pipeline disabled",
            resolved_core_env_file,
        )
        return ProcessingRuntime(platform=platform_runtime, processing=None)

    try:
        from passport_core import PassportWorkflow
        from passport_core.config import Settings as CoreSettings

        core_settings = cast(Any, CoreSettings)(_env_file=resolved_core_env_file)
        core_settings.assets_dir = _resolve(resolved_core_root_dir, core_settings.assets_dir)
        core_settings.template_path = _resolve(resolved_core_root_dir, core_settings.template_path)
        core_settings.face_model_path = _resolve(
            resolved_core_root_dir,
            core_settings.face_model_path,
        )
        workflow = PassportWorkflow(settings=core_settings)
    except Exception:
        log.exception("Failed to initialise passport-core — OCR pipeline disabled")
        return ProcessingRuntime(platform=platform_runtime, processing=None)

    processing = ProcessingService(
        users=platform_runtime.users,
        quotas=platform_runtime.quotas,
        uploads=platform_runtime.uploads,
        workflow=workflow,
        artifacts=platform_runtime.artifacts,
    )
    return ProcessingRuntime(platform=platform_runtime, processing=processing)


def build_processing_service(
    *,
    core_env_file: Path,
    core_root_dir: Path,
    platform_settings: PlatformSettings,
    db: Database,
) -> ProcessingService | None:
    """Backward-compatible wrapper around the shared runtime builders."""
    platform_runtime = _build_platform_runtime(settings=platform_settings, db=db)
    runtime = build_processing_runtime(
        platform_runtime=platform_runtime,
        core_env_file=core_env_file,
        core_root_dir=core_root_dir,
    )
    return runtime.processing


def _build_platform_runtime(*, settings: PlatformSettings, db: Database) -> PlatformRuntime:
    usage = UsageRepository(db)
    users = UserService(UsersRepository(db))
    quotas = QuotaService(usage)
    uploads = UploadService(UploadsRepository(db), usage)

    return PlatformRuntime(
        settings=settings,
        db=db,
        artifacts=LocalArtifactStore(settings.artifacts_dir),
        users=users,
        auth=AuthService(AuthTokensRepository(db), users),
        quotas=quotas,
        uploads=uploads,
        records=RecordsService(RecordsRepository(db)),
        reporting=ReportingService(
            users=users,
            quotas=quotas,
            reporting=ReportingRepository(db),
        ),
    )


def _resolve(root: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return (root / value).resolve()
