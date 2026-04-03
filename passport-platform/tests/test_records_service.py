from __future__ import annotations

from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.enums import ChannelName, ExternalProvider
from passport_platform.repositories.records import RecordsRepository
from passport_platform.repositories.uploads import UploadsRepository
from passport_platform.repositories.usage import UsageRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.schemas.commands import (
    EnsureUserCommand,
    RecordProcessingResultCommand,
    RegisterUploadCommand,
)
from passport_platform.services.records import RecordsService
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService


def _build_records_service(tmp_path):
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    records = RecordsService(RecordsRepository(db))
    return db, users, uploads, records


def _seed_user(users, external_user_id: str, display_name: str):
    return users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id=external_user_id,
            display_name=display_name,
        )
    )


def _register_processed_upload(
    uploads: UploadService,
    user_id: int,
    *,
    filename: str,
    source_ref: str,
    passport_number: str,
    review_status: str = "auto",
    extraction_result_json: str | None = None,
    completed_at: datetime | None = None,
):
    default_extraction_result = """
    {"data":{
        "GivenNameTokensAr":["عبد","الله"],
        "SurnameAr":"العمري",
        "GivenNameTokensEn":["ABDULLAH"],
        "SurnameEn":"ALOMARI",
        "PassportNumber":"12345678"
    }}
    """.strip()
    upload = uploads.register_upload(
        RegisterUploadCommand(
            user_id=user_id,
            channel=ChannelName.TELEGRAM,
            filename=filename,
            mime_type="image/jpeg",
            source_ref=source_ref,
        )
    )
    uploads.record_processing_result(
        user_id,
        RecordProcessingResultCommand(
            upload_id=upload.id,
            is_passport=True,
            is_complete=True,
            review_status=review_status,
            passport_number=passport_number,
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.97,
            extraction_result_json=extraction_result_json or default_extraction_result,
            completed_at=completed_at or datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        ),
    )
    return upload


def test_list_user_records_returns_only_owned_uploads(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    records = RecordsService(RecordsRepository(db))
    first_user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    second_user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="67890",
            display_name="Agency B",
        )
    )
    owned = uploads.register_upload(
        RegisterUploadCommand(
            user_id=first_user.id,
            channel=ChannelName.TELEGRAM,
            filename="owned.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://owned",
        )
    )
    uploads.record_processing_result(
        first_user.id,
        RecordProcessingResultCommand(
            upload_id=owned.id,
            is_passport=True,
            is_complete=True,
            review_status="auto",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.97,
            extraction_result_json='{"source":"telegram://owned","data":{"PassportNumber":"12345678"}}',
            completed_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        ),
    )
    other = uploads.register_upload(
        RegisterUploadCommand(
            user_id=second_user.id,
            channel=ChannelName.TELEGRAM,
            filename="other.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://other",
        )
    )
    uploads.record_processing_result(
        second_user.id,
        RecordProcessingResultCommand(
            upload_id=other.id,
            is_passport=False,
            is_complete=False,
            review_status="needs_review",
            error_code="not_passport",
            completed_at=datetime(2026, 3, 13, 12, 5, tzinfo=UTC),
        ),
    )

    user_records = records.list_user_records(first_user.id)

    assert len(user_records) == 1
    assert user_records[0].filename == "owned.jpg"
    assert user_records[0].passport_number == "12345678"
    assert user_records[0].passport_image_uri == "/tmp/original.jpg"
    assert user_records[0].confidence_overall == 0.97
    assert user_records[0].review_status == "auto"
    assert user_records[0].extraction_result is not None
    assert user_records[0].extraction_result["data"]["PassportNumber"] == "12345678"


def test_list_user_record_items_returns_slim_names(tmp_path) -> None:
    _, users, uploads, records = _build_records_service(tmp_path)
    user = _seed_user(users, "12345", "Agency A")
    _register_processed_upload(
        uploads,
        user.id,
        filename="owned.jpg",
        source_ref="telegram://owned",
        passport_number="12345678",
    )

    result = records.list_user_record_items(user.id, limit=50, offset=0, section="pending")

    assert result.items
    assert result.total == 1
    assert result.has_more is False
    assert result.items[0].passport_number == "12345678"
    assert result.items[0].full_name_ar == "عبد الله العمري"
    assert result.items[0].full_name_en == "ABDULLAH ALOMARI"


def test_count_user_record_sections_returns_pending_submitted_failed(tmp_path) -> None:
    _, users, uploads, records = _build_records_service(tmp_path)
    user = _seed_user(users, "12345", "Agency A")
    pending_upload = _register_processed_upload(
        uploads,
        user.id,
        filename="pending.jpg",
        source_ref="telegram://pending",
        passport_number="11111111",
    )
    submitted_upload = _register_processed_upload(
        uploads,
        user.id,
        filename="submitted.jpg",
        source_ref="telegram://submitted",
        passport_number="22222222",
    )
    failed_upload = _register_processed_upload(
        uploads,
        user.id,
        filename="failed.jpg",
        source_ref="telegram://failed",
        passport_number="33333333",
    )
    records.update_masar_status(
        upload_id=submitted_upload.id,
        user_id=user.id,
        status="submitted",
        masar_mutamer_id="M-1",
        masar_scan_result={"ok": True},
    )
    records.update_masar_status(
        upload_id=failed_upload.id,
        user_id=user.id,
        status="failed",
        masar_mutamer_id=None,
        masar_scan_result={"ok": False},
        failure_reason_code="submit-failed",
        failure_reason_text="Failed",
    )

    counts = records.count_user_record_sections(user.id)

    assert pending_upload.id != submitted_upload.id
    assert counts.pending == 1
    assert counts.submitted == 1
    assert counts.failed == 1


def test_list_submit_eligible_record_ids_excludes_review_blocked_records(tmp_path) -> None:
    _, users, uploads, records = _build_records_service(tmp_path)
    user = _seed_user(users, "12345", "Agency A")
    eligible_upload = _register_processed_upload(
        uploads,
        user.id,
        filename="eligible.jpg",
        source_ref="telegram://eligible",
        passport_number="11111111",
        review_status="auto",
    )
    _register_processed_upload(
        uploads,
        user.id,
        filename="blocked.jpg",
        source_ref="telegram://blocked",
        passport_number="22222222",
        review_status="needs_review",
    )

    result = records.list_submit_eligible_record_ids(user.id, limit=100, offset=0)

    assert result.total == 1
    assert result.has_more is False
    assert result.items == [
        type(result.items[0])(
            upload_id=eligible_upload.id,
            upload_status=result.items[0].upload_status,
            review_status="auto",
            masar_status=None,
        )
    ]


def test_update_masar_status_stores_detail_id_and_scan_result(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    records = RecordsService(RecordsRepository(db))
    user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    upload = uploads.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://passport",
        )
    )
    uploads.record_processing_result(
        user.id,
        RecordProcessingResultCommand(
            upload_id=upload.id,
            is_passport=True,
            is_complete=True,
            review_status="auto",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.97,
            extraction_result_json='{"data":{"PassportNumber":"12345678"}}',
            completed_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        ),
    )

    updated = records.update_masar_status(
        upload_id=upload.id,
        user_id=user.id,
        status="submitted",
        masar_mutamer_id="M-1",
        masar_scan_result={"ok": True},
        masar_detail_id="detail-123",
        submission_entity_id="819868",
        submission_entity_type_id="58",
        submission_entity_name="Agency Entity",
        submission_contract_id="222452",
        submission_contract_name="Contract A",
        submission_contract_name_ar="العقد أ",
        submission_contract_name_en="Contract A",
        submission_contract_number="0025",
        submission_contract_status=True,
        submission_uo_subscription_status_id=1,
        submission_group_id="group-22",
        submission_group_name="Group 22",
        submission_group_number="901675540",
        failure_reason_code=None,
        failure_reason_text=None,
    )
    record = records.get_user_record(user.id, upload.id)

    assert updated is True
    assert record is not None
    assert record.masar_status == "submitted"
    assert record.masar_mutamer_id == "M-1"
    assert record.masar_scan_result == {"ok": True}
    assert record.masar_detail_id == "detail-123"
    assert record.submission_entity_id == "819868"
    assert record.submission_entity_type_id == "58"
    assert record.submission_entity_name == "Agency Entity"
    assert record.submission_contract_id == "222452"
    assert record.submission_contract_name == "Contract A"
    assert record.submission_contract_name_ar == "العقد أ"
    assert record.submission_contract_name_en == "Contract A"
    assert record.submission_contract_number == "0025"
    assert record.submission_contract_status is True
    assert record.submission_uo_subscription_status_id == 1
    assert record.submission_group_id == "group-22"
    assert record.submission_group_name == "Group 22"
    assert record.submission_group_number == "901675540"
    assert record.failure_reason_code is None
    assert record.failure_reason_text is None


def test_update_masar_status_accepts_missing_state(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    records = RecordsService(RecordsRepository(db))
    user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    upload = uploads.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://passport",
        )
    )
    uploads.record_processing_result(
        user.id,
        RecordProcessingResultCommand(
            upload_id=upload.id,
            is_passport=True,
            is_complete=True,
            review_status="auto",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.97,
            extraction_result_json='{"data":{"PassportNumber":"12345678"}}',
            completed_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        ),
    )

    updated = records.update_masar_status(
        upload_id=upload.id,
        user_id=user.id,
        status="missing",
        masar_mutamer_id=None,
        masar_scan_result=None,
        masar_detail_id="detail-123",
        submission_entity_id="819868",
        submission_entity_type_id="58",
        submission_entity_name="Agency Entity",
        submission_contract_id="222452",
        submission_contract_name="Contract A",
        submission_group_id="group-22",
        submission_group_name="Group 22",
        submission_group_number="901675540",
        failure_reason_code="scan-image-unclear",
        failure_reason_text="Passport image is not clear",
    )
    record = records.get_user_record(user.id, upload.id)

    assert updated is True
    assert record is not None
    assert record.masar_status == "missing"
    assert record.masar_detail_id == "detail-123"
    assert record.submission_contract_id == "222452"
    assert record.submission_group_id == "group-22"
    assert record.failure_reason_code == "scan-image-unclear"
    assert record.failure_reason_text == "Passport image is not clear"


def test_assert_submission_allowed_accepts_needs_review_records(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    records = RecordsService(RecordsRepository(db))
    user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    upload = uploads.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://passport",
        )
    )
    uploads.record_processing_result(
        user.id,
        RecordProcessingResultCommand(
            upload_id=upload.id,
            is_passport=True,
            is_complete=True,
            review_status="needs_review",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.71,
            extraction_result_json='{"data":{"PassportNumber":"12345678"},"warnings":["requires_review"]}',
            completed_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        ),
    )

    records.assert_submission_allowed(upload_id=upload.id, user_id=user.id)
