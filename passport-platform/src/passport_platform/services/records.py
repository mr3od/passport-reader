from __future__ import annotations

import json

from passport_platform.errors import ReviewRequiredError
from passport_platform.repositories.records import RecordsRepository
from passport_platform.schemas.results import (
    UserRecord,
    UserRecordCounts,
    UserRecordIdListResult,
    UserRecordListResult,
)


class RecordsService:
    def __init__(self, records: RecordsRepository) -> None:
        self.records = records

    def list_user_records(self, user_id: int, *, limit: int = 50) -> list[UserRecord]:
        return self.records.list_user_records(user_id, limit=limit)

    def list_user_record_items(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
        section: str,
    ) -> UserRecordListResult:
        return self.records.list_user_record_items(
            user_id,
            limit=limit,
            offset=offset,
            section=section,
        )

    def count_user_record_sections(self, user_id: int) -> UserRecordCounts:
        return self.records.count_user_record_sections(user_id)

    def list_submit_eligible_record_ids(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> UserRecordIdListResult:
        return self.records.list_submit_eligible_record_ids(
            user_id,
            limit=limit,
            offset=offset,
        )

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
        submission_entity_id: str | None = None,
        submission_entity_type_id: str | None = None,
        submission_entity_name: str | None = None,
        submission_contract_id: str | None = None,
        submission_contract_name: str | None = None,
        submission_contract_name_ar: str | None = None,
        submission_contract_name_en: str | None = None,
        submission_contract_number: str | None = None,
        submission_contract_status: bool | None = None,
        submission_uo_subscription_status_id: int | None = None,
        submission_group_id: str | None = None,
        submission_group_name: str | None = None,
        submission_group_number: str | None = None,
        failure_reason_code: str | None = None,
        failure_reason_text: str | None = None,
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
            submission_entity_id=submission_entity_id,
            submission_entity_type_id=submission_entity_type_id,
            submission_entity_name=submission_entity_name,
            submission_contract_id=submission_contract_id,
            submission_contract_name=submission_contract_name,
            submission_contract_name_ar=submission_contract_name_ar,
            submission_contract_name_en=submission_contract_name_en,
            submission_contract_number=submission_contract_number,
            submission_contract_status=submission_contract_status,
            submission_uo_subscription_status_id=submission_uo_subscription_status_id,
            submission_group_id=submission_group_id,
            submission_group_name=submission_group_name,
            submission_group_number=submission_group_number,
            failure_reason_code=failure_reason_code,
            failure_reason_text=failure_reason_text,
        )

    def mark_reviewed(self, *, upload_id: int, user_id: int) -> bool:
        return self.records.mark_reviewed(upload_id=upload_id, user_id=user_id)

    def set_archive_state(
        self,
        *,
        upload_id: int,
        user_id: int,
        archived: bool,
    ) -> bool:
        return self.records.set_archive_state(
            upload_id=upload_id,
            user_id=user_id,
            archived=archived,
        )

    def assert_submission_allowed(self, *, upload_id: int, user_id: int) -> None:
        record = self.records.get_user_record(user_id, upload_id)
        if record is None:
            return
        if not record.is_complete:
            raise ReviewRequiredError()
        if record.review_status in {"auto", "reviewed", "needs_review"}:
            return
        raise ReviewRequiredError()
