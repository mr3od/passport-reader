from __future__ import annotations

from passport_platform.db import Database


def test_database_initializes_broadcasts_table(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")

    db.initialize()

    with db.connect() as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(broadcasts)").fetchall()
        }

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
