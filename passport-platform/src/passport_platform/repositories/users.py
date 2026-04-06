from __future__ import annotations

from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.enums import ExternalProvider, PlanName, UserStatus
from passport_platform.models.user import User


class UsersRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    external_provider,
                    external_user_id,
                    display_name,
                    plan,
                    status,
                    created_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        return _row_to_user(row)

    def get_by_external_identity(
        self,
        external_provider: ExternalProvider,
        external_user_id: str,
    ) -> User | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    external_provider,
                    external_user_id,
                    display_name,
                    plan,
                    status,
                    created_at
                FROM users
                WHERE external_provider = ? AND external_user_id = ?
                """,
                (external_provider.value, external_user_id),
            ).fetchone()
        return _row_to_user(row)

    def create(
        self,
        *,
        external_provider: ExternalProvider,
        external_user_id: str,
        display_name: str | None,
        plan: PlanName,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> User:
        created_at = datetime.now(UTC)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (
                    external_provider, external_user_id, display_name, plan, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    external_provider.value,
                    external_user_id,
                    display_name,
                    plan.value,
                    status.value,
                    created_at.isoformat(),
                ),
            )
            assert cursor.lastrowid is not None
            user_id = cursor.lastrowid
        user = self.get_by_id(user_id)
        if user is None:
            raise RuntimeError("created user could not be loaded")
        return user

    def list_all(self, *, limit: int = 50) -> list[User]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    external_provider,
                    external_user_id,
                    display_name,
                    plan,
                    status,
                    created_at
                FROM users
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [user for row in rows if (user := _row_to_user(row)) is not None]

    def list_active_by_provider(self, external_provider: ExternalProvider) -> list[User]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    external_provider,
                    external_user_id,
                    display_name,
                    plan,
                    status,
                    created_at
                FROM users
                WHERE external_provider = ? AND status = ?
                ORDER BY created_at ASC, id ASC
                """,
                (external_provider.value, UserStatus.ACTIVE.value),
            ).fetchall()
        return [user for row in rows if (user := _row_to_user(row)) is not None]

    def update_plan(self, user_id: int, plan: PlanName) -> User:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE users SET plan = ? WHERE id = ?",
                (plan.value, user_id),
            )
        user = self.get_by_id(user_id)
        if user is None:
            raise KeyError(f"user {user_id} not found")
        return user

    def update_status(self, user_id: int, status: UserStatus) -> User:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE users SET status = ? WHERE id = ?",
                (status.value, user_id),
            )
        user = self.get_by_id(user_id)
        if user is None:
            raise KeyError(f"user {user_id} not found")
        return user


def _row_to_user(row) -> User | None:
    if row is None:
        return None
    return User(
        id=int(row["id"]),
        external_provider=ExternalProvider(row["external_provider"]),
        external_user_id=row["external_user_id"],
        display_name=row["display_name"],
        plan=PlanName(row["plan"]),
        status=UserStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
