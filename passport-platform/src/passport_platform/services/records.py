from __future__ import annotations

from passport_platform.repositories.records import RecordsRepository
from passport_platform.schemas.results import UserRecord


class RecordsService:
    def __init__(self, records: RecordsRepository) -> None:
        self.records = records

    def list_user_records(self, user_id: int, *, limit: int = 50) -> list[UserRecord]:
        return self.records.list_user_records(user_id, limit=limit)
