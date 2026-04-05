from __future__ import annotations

from passport_platform.enums import ExternalProvider
from passport_platform.models.broadcast import Broadcast, BroadcastContentType
from passport_platform.repositories.broadcasts import BroadcastsRepository
from passport_platform.services.users import UserService
from passport_platform.storage import ArtifactStore


class BroadcastService:
    def __init__(
        self,
        broadcasts: BroadcastsRepository,
        users: UserService,
        artifacts: ArtifactStore,
    ) -> None:
        self.broadcasts = broadcasts
        self.users = users
        self.artifacts = artifacts

    def create_text_broadcast(
        self, *, created_by_external_user_id: str, text_body: str
    ) -> Broadcast:
        return self.broadcasts.create(
            created_by_external_user_id=created_by_external_user_id,
            content_type=BroadcastContentType.TEXT,
            text_body=text_body,
            caption=None,
            artifact_path=None,
        )

    def create_photo_broadcast(
        self,
        *,
        created_by_external_user_id: str,
        photo_bytes: bytes,
        filename: str,
        content_type: str,
        caption: str | None,
    ) -> Broadcast:
        artifact_path = self.artifacts.save(
            photo_bytes,
            folder="broadcasts",
            filename=filename,
            content_type=content_type,
        )
        return self.broadcasts.create(
            created_by_external_user_id=created_by_external_user_id,
            content_type=BroadcastContentType.PHOTO,
            text_body=None,
            caption=caption,
            artifact_path=artifact_path,
        )

    def claim_next_pending_broadcast(self) -> Broadcast | None:
        total_targets = len(self.users.list_active_users_by_provider(ExternalProvider.TELEGRAM))
        return self.broadcasts.claim_next_pending(total_targets=total_targets)

    def mark_completed(self, broadcast_id: int, *, sent_count: int, failed_count: int) -> Broadcast:
        return self.broadcasts.mark_completed(
            broadcast_id,
            sent_count=sent_count,
            failed_count=failed_count,
        )

    def mark_failed(self, broadcast_id: int, *, error_message: str) -> Broadcast:
        return self.broadcasts.mark_failed(broadcast_id, error_message=error_message)
