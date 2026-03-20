from __future__ import annotations

import logging
from pathlib import Path

from passport_platform.config import PlatformSettings
from passport_platform.db import Database
from passport_platform.repositories.uploads import UploadsRepository
from passport_platform.repositories.usage import UsageRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.services.processing import ProcessingService
from passport_platform.services.quotas import QuotaService
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService
from passport_platform.storage import LocalArtifactStore

log = logging.getLogger(__name__)


def build_processing_service(
    *,
    core_env_file: Path,
    core_root_dir: Path,
    platform_settings: PlatformSettings,
    db: Database,
) -> ProcessingService | None:
    """Build a ProcessingService wired to passport-core.

    Returns None if passport-core is not configured (missing .env or import error),
    so callers can degrade gracefully without crashing.
    """
    if not core_env_file.exists():
        log.info("passport-core .env not found at %s — OCR pipeline disabled", core_env_file)
        return None
    try:
        from passport_core import PassportWorkflow
        from passport_core.config import Settings as CoreSettings

        core_settings = CoreSettings(_env_file=core_env_file)
        core_settings.assets_dir = _resolve(core_root_dir, core_settings.assets_dir)
        core_settings.template_path = _resolve(core_root_dir, core_settings.template_path)
        core_settings.face_model_path = _resolve(core_root_dir, core_settings.face_model_path)
        workflow = PassportWorkflow(settings=core_settings)
    except Exception:
        log.exception("Failed to initialise passport-core — OCR pipeline disabled")
        return None

    usage = UsageRepository(db)
    users = UserService(UsersRepository(db))
    return ProcessingService(
        users=users,
        quotas=QuotaService(usage),
        uploads=UploadService(UploadsRepository(db), usage),
        workflow=workflow,
        artifacts=LocalArtifactStore(platform_settings.artifacts_dir),
    )


def _resolve(root: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return (root / value).resolve()
