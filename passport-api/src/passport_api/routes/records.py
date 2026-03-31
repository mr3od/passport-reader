from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from passport_platform import AuthenticatedSession, ProcessUploadCommand, ReviewRequiredError
from passport_platform.enums import ChannelName, ExternalProvider, PlanName
from passport_platform.strings import (
    RECORD_IMAGE_NOT_ON_DISK,
    RECORD_NO_IMAGE,
    RECORD_NOT_FOUND,
    RECORD_REVIEW_REQUIRED,
)

from passport_api.deps import get_api_services, get_authenticated_session
from passport_api.schemas import MasarStatusUpdate, RecordResponse, ReviewStatusUpdate
from passport_api.services import ApiServices

router = APIRouter(tags=["records"])


@router.post("/records/upload", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
def upload_record(
    file: UploadFile,
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> RecordResponse:
    if services.processing is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR pipeline not configured",
        )
    payload = file.file.read()
    result = services.processing.process_bytes(
        ProcessUploadCommand(
            external_provider=ExternalProvider.API,
            external_user_id=authenticated.user.external_user_id,
            channel=ChannelName.API,
            filename=file.filename or "upload.jpg",
            mime_type=file.content_type or "image/jpeg",
            source_ref="api-upload",
            payload=payload,
            display_name=authenticated.user.display_name,
            default_plan=PlanName.PRO,
        )
    )
    records = services.records.list_user_records(authenticated.user.id, limit=200)
    record = next((r for r in records if r.upload_id == result.upload.id), None)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="record not found after processing",
        )
    return _record_to_response(record)


@router.get("/records", response_model=list[RecordResponse])
def list_records(
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RecordResponse]:
    records = services.records.list_user_records(authenticated.user.id, limit=limit)
    return [_record_to_response(record) for record in records]


@router.get("/records/masar/pending", response_model=list[RecordResponse])
def list_masar_pending(
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> list[RecordResponse]:
    records = services.records.get_masar_pending(authenticated.user.id)
    return [_record_to_response(record) for record in records]


@router.get("/records/{upload_id}", response_model=RecordResponse)
def get_record(
    upload_id: int,
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> RecordResponse:
    record = services.records.get_user_record(authenticated.user.id, upload_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RECORD_NOT_FOUND)
    return _record_to_response(record)


@router.get("/records/{upload_id}/image")
def get_record_image(
    upload_id: int,
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> FileResponse:
    record = services.records.get_user_record(authenticated.user.id, upload_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RECORD_NOT_FOUND)
    uri = record.passport_image_uri
    if not uri:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RECORD_NO_IMAGE)
    path = Path(uri)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RECORD_IMAGE_NOT_ON_DISK)
    return FileResponse(path, media_type=record.mime_type or "image/jpeg")


@router.patch("/records/{upload_id}/masar-status", response_model=RecordResponse)
def update_masar_status(
    upload_id: int,
    body: MasarStatusUpdate,
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> RecordResponse:
    if body.status not in ("submitted", "failed"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be 'submitted' or 'failed'",
        )
    if body.status == "submitted":
        try:
            services.records.assert_submission_allowed(
                upload_id=upload_id,
                user_id=authenticated.user.id,
            )
        except ReviewRequiredError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    updated = services.records.update_masar_status(
        upload_id=upload_id,
        user_id=authenticated.user.id,
        status=body.status,
        masar_mutamer_id=body.masar_mutamer_id,
        masar_scan_result=body.masar_scan_result,
        masar_detail_id=body.masar_detail_id,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RECORD_NOT_FOUND)
    records = services.records.list_user_records(authenticated.user.id, limit=200)
    for record in records:
        if record.upload_id == upload_id:
            return _record_to_response(record)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RECORD_NOT_FOUND)


@router.patch("/records/{upload_id}/review-status", response_model=RecordResponse)
def update_review_status(
    upload_id: int,
    body: ReviewStatusUpdate,
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> RecordResponse:
    if body.status != "reviewed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be 'reviewed'",
        )
    record = services.records.get_user_record(authenticated.user.id, upload_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RECORD_NOT_FOUND)
    if record.review_status != "needs_review":
        return _record_to_response(record)
    updated = services.records.mark_reviewed(upload_id=upload_id, user_id=authenticated.user.id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RECORD_NOT_FOUND)
    updated_record = services.records.get_user_record(authenticated.user.id, upload_id)
    if updated_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RECORD_NOT_FOUND)
    return _record_to_response(updated_record)


def _record_to_response(record) -> RecordResponse:
    return RecordResponse(
        upload_id=record.upload_id,
        user_id=record.user_id,
        filename=record.filename,
        mime_type=record.mime_type,
        source_ref=record.source_ref,
        upload_status=record.upload_status.value,
        created_at=record.created_at,
        completed_at=record.completed_at,
        is_passport=record.is_passport,
        is_complete=record.is_complete,
        review_status=record.review_status,
        passport_number=record.passport_number,
        passport_image_uri=record.passport_image_uri,
        confidence_overall=record.confidence_overall,
        review_summary=_review_summary(record),
        extraction_result=record.extraction_result,
        error_code=record.error_code,
        masar_status=record.masar_status,
        masar_detail_id=record.masar_detail_id,
    )


def _review_summary(record) -> str | None:
    if record.review_status != "needs_review":
        return None
    return RECORD_REVIEW_REQUIRED
