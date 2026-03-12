from __future__ import annotations

from passport_platform.db import Database
from passport_platform.enums import ExternalProvider, PlanName, UserStatus
from passport_platform.repositories.users import UsersRepository
from passport_platform.schemas.commands import EnsureUserCommand
from passport_platform.services.users import UserService


def test_get_or_create_user_is_idempotent(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    service = UserService(UsersRepository(db))

    command = EnsureUserCommand(
        external_provider=ExternalProvider.TELEGRAM,
        external_user_id="12345",
        display_name="Agency A",
    )
    first = service.get_or_create_user(command)
    second = service.get_or_create_user(command)

    assert first.id == second.id
    assert second.plan is PlanName.FREE
    assert second.display_name == "Agency A"


def test_change_plan_updates_existing_user(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UsersRepository(db)
    service = UserService(users)
    user = service.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
        )
    )

    updated = service.change_plan(user.id, PlanName.PRO)

    assert updated.plan is PlanName.PRO


def test_list_users_and_change_status_are_available_for_admin_flows(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    service = UserService(UsersRepository(db))
    created = service.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )

    listed = service.list_users(limit=10)
    updated = service.change_status(created.id, UserStatus.BLOCKED)

    assert listed[0].id == created.id
    assert service.get_by_id(created.id) is not None
    assert updated.status is UserStatus.BLOCKED
