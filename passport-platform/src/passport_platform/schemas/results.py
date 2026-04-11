from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, Field

from passport_platform.enums import PlanName, UploadStatus, UserStatus
from passport_platform.models.upload import ProcessingResult, Upload
from passport_platform.models.user import User

if TYPE_CHECKING:
    from passport_core.extraction.models import ExtractionResult
else:
    ExtractionResult = Any


class PassportExtractionView(BaseModel):
    """Adapter-safe projection of extracted passport data."""

    passport_number: str | None = None
    country_code: str | None = None
    surname_ar: str | None = None
    given_names_ar: str | None = None
    given_name_tokens_ar: list[str] = Field(default_factory=list)
    full_name_ar: str | None = None
    surname_en: str | None = None
    given_names_en: str | None = None
    given_name_tokens_en: list[str] = Field(default_factory=list)
    full_name_en: str | None = None
    date_of_birth: str | None = None
    place_of_birth_ar: str | None = None
    place_of_birth_en: str | None = None
    birth_city_ar: str | None = None
    birth_city_en: str | None = None
    birth_country_ar: str | None = None
    birth_country_en: str | None = None
    sex: str | None = None
    date_of_issue: str | None = None
    date_of_expiry: str | None = None
    profession_ar: str | None = None
    profession_en: str | None = None
    issuing_authority_ar: str | None = None
    issuing_authority_en: str | None = None


@dataclass(slots=True)
class QuotaDecision:
    allowed: bool
    plan: PlanName
    monthly_upload_limit: int
    monthly_uploads_used: int
    monthly_success_limit: int
    monthly_successes_used: int
    remaining_uploads: int
    remaining_successes: int
    max_batch_size: int
    reason: str | None = None


@dataclass(slots=True)
class TrackedProcessingResult:
    user: User
    upload: Upload
    quota_decision: QuotaDecision
    extraction_result: ExtractionResult | None
    processing_result: ProcessingResult

    @property
    def filename(self) -> str:
        return self.upload.filename

    @property
    def mime_type(self) -> str:
        return self.upload.mime_type

    @property
    def source_ref(self) -> str:
        return self.upload.source_ref

    @property
    def is_passport(self) -> bool:
        return self.processing_result.is_passport

    @property
    def is_complete(self) -> bool:
        return self.processing_result.is_complete

    @property
    def confidence_overall(self) -> float | None:
        return self.processing_result.confidence_overall

    @property
    def review_status(self) -> str:
        return self.processing_result.review_status

    @property
    def warnings(self) -> list[str]:
        if self.extraction_result is None:
            return []
        return list(self.extraction_result.warnings or [])

    @property
    def extracted_data(self) -> PassportExtractionView | None:
        if self.extraction_result is None:
            return None
        return _build_extraction_view(self.extraction_result.data)


@dataclass(slots=True)
class UserUsageReport:
    user: User
    quota_decision: QuotaDecision
    period_start: datetime
    period_end: datetime
    upload_count: int
    success_count: int
    failure_count: int


@dataclass(slots=True)
class MonthlyUsageReport:
    period_start: datetime
    period_end: datetime
    total_users: int
    active_users: int
    blocked_users: int
    total_uploads: int
    total_successes: int
    total_failures: int


@dataclass(slots=True)
class RecentUploadRecord:
    upload_id: int
    user_id: int
    external_provider: str
    external_user_id: str
    display_name: str | None
    plan: PlanName
    user_status: UserStatus
    filename: str
    source_ref: str
    upload_status: UploadStatus
    passport_number: str | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(slots=True)
class UserRecord:
    upload_id: int
    user_id: int
    filename: str
    mime_type: str
    source_ref: str
    upload_status: UploadStatus
    created_at: datetime
    archived_at: datetime | None
    completed_at: datetime | None
    is_passport: bool | None
    is_complete: bool | None
    review_status: str | None
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    passport_number: str | None
    passport_image_uri: str | None
    confidence_overall: float | None
    extraction_result: dict[str, Any] | None
    error_code: str | None
    masar_status: str | None
    masar_mutamer_id: str | None
    masar_scan_result: dict[str, Any] | None
    masar_detail_id: str | None
    submission_entity_id: str | None
    submission_entity_type_id: str | None
    submission_entity_name: str | None
    submission_contract_id: str | None
    submission_contract_name: str | None
    submission_contract_name_ar: str | None
    submission_contract_name_en: str | None
    submission_contract_number: str | None
    submission_contract_status: bool | None
    submission_uo_subscription_status_id: int | None
    submission_group_id: str | None
    submission_group_name: str | None
    submission_group_number: str | None
    failure_reason_code: str | None
    failure_reason_text: str | None


@dataclass(slots=True)
class UserRecordListItem:
    upload_id: int
    filename: str
    upload_status: UploadStatus
    review_status: str | None
    masar_status: str | None
    masar_detail_id: str | None
    passport_number: str | None
    full_name_ar: str | None
    full_name_en: str | None
    created_at: datetime
    archived_at: datetime | None
    completed_at: datetime | None
    failure_reason_code: str | None
    failure_reason_text: str | None


@dataclass(slots=True)
class UserRecordListResult:
    items: list[UserRecordListItem]
    total: int
    has_more: bool


@dataclass(slots=True)
class UserRecordCounts:
    pending: int
    submitted: int
    failed: int


@dataclass(slots=True)
class UserRecordIdItem:
    upload_id: int
    upload_status: UploadStatus
    review_status: str | None
    masar_status: str | None


@dataclass(slots=True)
class UserRecordIdListResult:
    items: list[UserRecordIdItem]
    total: int
    has_more: bool


def _build_extraction_view(data: object | None) -> PassportExtractionView | None:
    """Map v2 passport-core fields into a stable adapter view."""
    if data is None:
        return None

    given_name_tokens_ar = _token_list_value(data, "GivenNameTokensAr")
    given_name_tokens_en = _token_list_value(data, "GivenNameTokensEn")
    given_names_ar = _join_tokens(given_name_tokens_ar)
    given_names_en = _join_tokens(given_name_tokens_en)
    surname_ar = _string_value(data, "SurnameAr")
    surname_en = _string_value(data, "SurnameEn")

    return PassportExtractionView(
        passport_number=_string_value(data, "PassportNumber"),
        country_code=_string_value(data, "CountryCode"),
        surname_ar=surname_ar,
        given_names_ar=given_names_ar,
        given_name_tokens_ar=given_name_tokens_ar,
        full_name_ar=_join_values(given_names_ar, surname_ar),
        surname_en=surname_en,
        given_names_en=given_names_en,
        given_name_tokens_en=given_name_tokens_en,
        full_name_en=_join_values(given_names_en, surname_en),
        date_of_birth=_string_value(data, "DateOfBirth"),
        place_of_birth_ar=_string_value(data, "PlaceOfBirthAr"),
        place_of_birth_en=_string_value(data, "PlaceOfBirthEn"),
        birth_city_ar=_string_value(data, "BirthCityAr"),
        birth_city_en=_string_value(data, "BirthCityEn"),
        birth_country_ar=_string_value(data, "BirthCountryAr"),
        birth_country_en=_string_value(data, "BirthCountryEn"),
        sex=_string_value(data, "Sex"),
        date_of_issue=_string_value(data, "DateOfIssue"),
        date_of_expiry=_string_value(data, "DateOfExpiry"),
        profession_ar=_string_value(data, "ProfessionAr"),
        profession_en=_string_value(data, "ProfessionEn"),
        issuing_authority_ar=_string_value(data, "IssuingAuthorityAr"),
        issuing_authority_en=_string_value(data, "IssuingAuthorityEn"),
    )


def _data_value(data: object, field_name: str) -> object | None:
    if isinstance(data, dict):
        return cast(dict[str, object], data).get(field_name)
    return getattr(data, field_name, None)


def _string_value(data: object, field_name: str) -> str | None:
    value = _data_value(data, field_name)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _token_list_value(data: object, field_name: str) -> list[str]:
    value = _data_value(data, field_name)
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _join_tokens(values: list[str]) -> str | None:
    if not values:
        return None
    return " ".join(values)


def _join_values(*values: str | None) -> str | None:
    normalized = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if not normalized:
        return None
    return " ".join(normalized)
