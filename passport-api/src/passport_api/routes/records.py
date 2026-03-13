from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from passport_api.deps import get_api_services, get_authenticated_session
from passport_api.schemas import RecordResponse
from passport_api.services import ApiServices

router = APIRouter(tags=["records"])


@router.get("/records", response_model=list[RecordResponse])
def list_records(
    authenticated: Annotated[object, Depends(get_authenticated_session)],
    services: Annotated[ApiServices, Depends(get_api_services)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RecordResponse]:
    records = services.records.list_user_records(authenticated.user.id, limit=limit)
    return [
        RecordResponse(
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
        )
        for record in records
    ]
