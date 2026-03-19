from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from passport_api.deps import get_api_services, get_authenticated_session
from passport_api.schemas import MasarStatusUpdate, RecordResponse
from passport_api.services import ApiServices

router = APIRouter(tags=["records"])


@router.get("/records", response_model=list[RecordResponse])
def list_records(
    authenticated: Annotated[object, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RecordResponse]:
    records = services.records.list_user_records(authenticated.user.id, limit=limit)
    return [_record_to_response(record) for record in records]


@router.get("/records/masar/pending", response_model=list[RecordResponse])
def list_masar_pending(
    authenticated: Annotated[object, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> list[RecordResponse]:
    records = services.records.get_masar_pending(authenticated.user.id)
    return [_record_to_response(record) for record in records]


@router.patch("/records/{upload_id}/masar-status", response_model=RecordResponse)
def update_masar_status(
    upload_id: int,
    body: MasarStatusUpdate,
    authenticated: Annotated[object, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> RecordResponse:
    if body.status not in ("submitted", "failed"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be 'submitted' or 'failed'",
        )
    updated = services.records.update_masar_status(
        upload_id=upload_id,
        user_id=authenticated.user.id,
        status=body.status,
        masar_mutamer_id=body.masar_mutamer_id,
        masar_scan_result=body.masar_scan_result,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
    records = services.records.list_user_records(authenticated.user.id, limit=200)
    for record in records:
        if record.upload_id == upload_id:
            return _record_to_response(record)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")


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
        has_face=record.has_face,
        is_complete=record.is_complete,
        passport_number=record.passport_number,
        passport_image_uri=record.passport_image_uri,
        face_crop_uri=record.face_crop_uri,
        core_result=record.core_result,
        error_code=record.error_code,
        masar_status=record.masar_status,
    )
