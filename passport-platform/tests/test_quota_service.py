from __future__ import annotations

from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.enums import ExternalProvider, PlanName, UsageEventType
from passport_platform.repositories.usage import UsageRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.schemas.commands import EnsureUserCommand
from passport_platform.services.quotas import QuotaService
from passport_platform.services.users import UserService


def test_free_plan_allows_uploads_when_under_limit(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    user_service = UserService(UsersRepository(db))
    quota_service = QuotaService(UsageRepository(db))
    user = user_service.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
        )
    )

    decision = quota_service.evaluate_user_quota(user, at=datetime(2026, 3, 1, tzinfo=UTC))

    assert decision.allowed is True
    assert decision.remaining_uploads == 20
    assert decision.max_batch_size == 2


def test_free_plan_blocks_when_monthly_upload_limit_is_reached(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    user_service = UserService(UsersRepository(db))
    usage = UsageRepository(db)
    quota_service = QuotaService(usage)
    user = user_service.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
        )
    )
    now = datetime(2026, 3, 15, 9, 0, tzinfo=UTC)
    for _ in range(20):
        usage.record(
            user_id=user.id,
            event_type=UsageEventType.UPLOAD_RECEIVED,
            created_at=now,
        )

    decision = quota_service.evaluate_user_quota(user, at=now)

    assert decision.allowed is False
    assert decision.remaining_uploads == 0
    assert decision.reason == "monthly upload quota reached"


def test_free_plan_blocks_when_monthly_success_limit_is_reached(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UsersRepository(db)
    user_service = UserService(users)
    usage = UsageRepository(db)
    quota_service = QuotaService(usage)
    user = user_service.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            default_plan=PlanName.FREE,
        )
    )
    now = datetime(2026, 3, 15, 9, 0, tzinfo=UTC)
    for _ in range(20):
        usage.record(
            user_id=user.id,
            event_type=UsageEventType.SUCCESSFUL_PROCESS,
            created_at=now,
        )

    decision = quota_service.evaluate_user_quota(user, at=now)

    assert decision.allowed is False
    assert decision.remaining_successes == 0
    assert decision.reason == "monthly success quota reached"
