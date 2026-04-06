from __future__ import annotations

from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.models.broadcast import Broadcast, BroadcastContentType, BroadcastStatus


class BroadcastsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(
        self,
        *,
        created_by_external_user_id: str,
        content_type: BroadcastContentType,
        text_body: str | None,
        caption: str | None,
        artifact_path: str | None,
    ) -> Broadcast:
        created_at = datetime.now(UTC)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO broadcasts (
                    created_by_external_user_id,
                    content_type,
                    text_body,
                    caption,
                    artifact_path,
                    status,
                    total_targets,
                    sent_count,
                    failed_count,
                    error_message,
                    created_at,
                    started_at,
                    completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, NULL, ?, NULL, NULL)
                """,
                (
                    created_by_external_user_id,
                    content_type.value,
                    text_body,
                    caption,
                    artifact_path,
                    BroadcastStatus.PENDING.value,
                    created_at.isoformat(),
                ),
            )
            assert cursor.lastrowid is not None
            broadcast_id = cursor.lastrowid
        loaded = self.get_by_id(broadcast_id)
        if loaded is None:
            raise RuntimeError("created broadcast could not be loaded")
        return loaded

    def get_by_id(self, broadcast_id: int) -> Broadcast | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM broadcasts WHERE id = ?", (broadcast_id,)).fetchone()
        return _row_to_broadcast(row)

    def claim_next_pending(self, *, total_targets: int) -> Broadcast | None:
        started_at = datetime.now(UTC)
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                """
                SELECT *
                FROM broadcasts
                WHERE status = ?
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (BroadcastStatus.PENDING.value,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE broadcasts
                SET status = ?, total_targets = ?, started_at = ?
                WHERE id = ?
                """,
                (
                    BroadcastStatus.PROCESSING.value,
                    total_targets,
                    started_at.isoformat(),
                    row["id"],
                ),
            )
            claimed = conn.execute("SELECT * FROM broadcasts WHERE id = ?", (row["id"],)).fetchone()
        return _row_to_broadcast(claimed)

    def mark_completed(self, broadcast_id: int, *, sent_count: int, failed_count: int) -> Broadcast:
        completed_at = datetime.now(UTC)
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE broadcasts
                SET status = ?,
                    sent_count = ?,
                    failed_count = ?,
                    completed_at = ?,
                    error_message = NULL
                WHERE id = ?
                """,
                (
                    BroadcastStatus.COMPLETED.value,
                    sent_count,
                    failed_count,
                    completed_at.isoformat(),
                    broadcast_id,
                ),
            )
        loaded = self.get_by_id(broadcast_id)
        if loaded is None:
            raise KeyError(f"broadcast {broadcast_id} not found")
        return loaded

    def mark_failed(self, broadcast_id: int, *, error_message: str) -> Broadcast:
        completed_at = datetime.now(UTC)
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE broadcasts
                SET status = ?, error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    BroadcastStatus.FAILED.value,
                    error_message,
                    completed_at.isoformat(),
                    broadcast_id,
                ),
            )
        loaded = self.get_by_id(broadcast_id)
        if loaded is None:
            raise KeyError(f"broadcast {broadcast_id} not found")
        return loaded


def _row_to_broadcast(row) -> Broadcast | None:
    if row is None:
        return None
    return Broadcast(
        id=int(row["id"]),
        created_by_external_user_id=row["created_by_external_user_id"],
        content_type=BroadcastContentType(row["content_type"]),
        text_body=row["text_body"],
        caption=row["caption"],
        artifact_path=row["artifact_path"],
        status=BroadcastStatus(row["status"]),
        total_targets=int(row["total_targets"]),
        sent_count=int(row["sent_count"]),
        failed_count=int(row["failed_count"]),
        error_message=row["error_message"],
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )
