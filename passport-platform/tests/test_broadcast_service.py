from __future__ import annotations

from passport_platform.db import Database
from passport_platform.enums import ExternalProvider, PlanName
from passport_platform.repositories.broadcasts import BroadcastsRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.services.broadcasts import BroadcastService
from passport_platform.services.users import UserService
from passport_platform.storage import LocalArtifactStore


def test_database_initializes_broadcasts_table(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")

    db.initialize()

    with db.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(broadcasts)").fetchall()}

    assert {
        "id",
        "created_by_external_user_id",
        "content_type",
        "text_body",
        "caption",
        "artifact_path",
        "status",
        "total_targets",
        "sent_count",
        "failed_count",
        "error_message",
        "created_at",
        "started_at",
        "completed_at",
    } <= columns


def test_create_text_broadcast_persists_pending_record(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    service = BroadcastService(
        broadcasts=BroadcastsRepository(db),
        users=UserService(UsersRepository(db)),
        artifacts=LocalArtifactStore(tmp_path / "artifacts"),
    )

    created = service.create_text_broadcast(
        created_by_external_user_id="777",
        text_body="Maintenance tonight",
    )

    assert created.content_type.value == "text"
    assert created.status.value == "pending"
    assert created.text_body == "Maintenance tonight"
    assert created.total_targets == 0


def test_create_photo_broadcast_stores_artifact(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    service = BroadcastService(
        broadcasts=BroadcastsRepository(db),
        users=UserService(UsersRepository(db)),
        artifacts=LocalArtifactStore(tmp_path / "artifacts"),
    )

    created = service.create_photo_broadcast(
        created_by_external_user_id="777",
        photo_bytes=b"fake-image",
        filename="notice.jpg",
        content_type="image/jpeg",
        caption="Read this",
    )

    assert created.content_type.value == "photo"
    assert created.caption == "Read this"
    assert created.artifact_path is not None


def test_claim_next_pending_broadcast_marks_processing(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UsersRepository(db)
    users.create(
        external_provider=ExternalProvider.TELEGRAM,
        external_user_id="100",
        display_name="Agency A",
        plan=PlanName.FREE,
    )
    service = BroadcastService(
        broadcasts=BroadcastsRepository(db),
        users=UserService(users),
        artifacts=LocalArtifactStore(tmp_path / "artifacts"),
    )
    service.create_text_broadcast(
        created_by_external_user_id="777",
        text_body="Maintenance tonight",
    )

    claimed = service.claim_next_pending_broadcast()

    assert claimed is not None
    assert claimed.status.value == "processing"
    assert claimed.total_targets == 1


def test_complete_broadcast_updates_delivery_counts(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    service = BroadcastService(
        broadcasts=BroadcastsRepository(db),
        users=UserService(UsersRepository(db)),
        artifacts=LocalArtifactStore(tmp_path / "artifacts"),
    )
    created = service.create_text_broadcast(
        created_by_external_user_id="777",
        text_body="Maintenance tonight",
    )

    updated = service.mark_completed(created.id, sent_count=3, failed_count=1)

    assert updated.status.value == "completed"
    assert updated.sent_count == 3
    assert updated.failed_count == 1
    assert updated.completed_at is not None
