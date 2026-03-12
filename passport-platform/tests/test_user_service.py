from __future__ import annotations

from passport_platform.db import Database
from passport_platform.enums import ExternalProvider, PlanName
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
