from __future__ import annotations

from passport_platform.enums import ExternalProvider, PlanName
from passport_platform.models.user import User
from passport_platform.repositories.users import UsersRepository
from passport_platform.schemas.commands import EnsureUserCommand


class UserService:
    def __init__(self, users: UsersRepository) -> None:
        self.users = users

    def get_or_create_user(self, command: EnsureUserCommand) -> User:
        existing = self.users.get_by_external_identity(
            command.external_provider,
            command.external_user_id,
        )
        if existing is not None:
            return existing
        return self.users.create(
            external_provider=command.external_provider,
            external_user_id=command.external_user_id,
            display_name=command.display_name,
            plan=command.default_plan,
        )

    def get_by_external_identity(
        self,
        external_provider: ExternalProvider,
        external_user_id: str,
    ) -> User | None:
        return self.users.get_by_external_identity(external_provider, external_user_id)

    def change_plan(self, user_id: int, plan: PlanName) -> User:
        return self.users.update_plan(user_id, plan)
