from __future__ import annotations

import json

from passport_platform.errors import ReviewRequiredError
from passport_platform.repositories.records import RecordsRepository
from passport_platform.schemas.results import UserRecord


class RecordsService:
    def __init__(self, records: RecordsRepository) -> None:
        self.records = records

    def list_user_records(self, user_id: int, *, limit: int = 50) -> list[UserRecord]:
        return self.records.list_user_records(user_id, limit=limit)

    def get_user_record(self, user_id: int, upload_id: int) -> UserRecord | None:
        return self.records.get_user_record(user_id, upload_id)

    def get_masar_pending(self, user_id: int) -> list[UserRecord]:
        return self.records.get_masar_pending(user_id)

    def update_masar_status(
        self,
        upload_id: int,
        user_id: int,
        status: str,
        masar_mutamer_id: str | None,
        masar_scan_result: dict | None,
        masar_detail_id: str | None = None,
    ) -> bool:
        masar_scan_result_json = (
            json.dumps(masar_scan_result) if masar_scan_result is not None else None
        )
        return self.records.insert_masar_submission(
            upload_id=upload_id,
            user_id=user_id,
            status=status,
            masar_mutamer_id=masar_mutamer_id,
            masar_scan_result_json=masar_scan_result_json,
            masar_detail_id=masar_detail_id,
        )

    def mark_reviewed(self, *, upload_id: int, user_id: int) -> bool:
        return self.records.mark_reviewed(upload_id=upload_id, user_id=user_id)

    def assert_submission_allowed(self, *, upload_id: int, user_id: int) -> None:
        record = self.records.get_user_record(user_id, upload_id)
        if record is None:
            return
        if not record.is_complete:
            raise ReviewRequiredError()
        if record.review_status in {"auto", "reviewed", "needs_review"}:
            return
        raise ReviewRequiredError()
