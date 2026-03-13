from __future__ import annotations

import sqlite3
from contextlib import nullcontext
from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.enums import UsageEventType
from passport_platform.models.usage import UsageLedgerEntry


class UsageRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(
        self,
        *,
        user_id: int,
        event_type: UsageEventType,
        units: int = 1,
        upload_id: int | None = None,
        created_at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> UsageLedgerEntry:
        created_at = created_at or datetime.now(UTC)
        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as active_conn:
            cursor = active_conn.execute(
                """
                INSERT INTO usage_ledger (user_id, upload_id, event_type, units, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    upload_id,
                    event_type.value,
                    units,
                    created_at.isoformat(),
                ),
            )
            entry_id = int(cursor.lastrowid)
        if conn is not None:
            return UsageLedgerEntry(
                id=entry_id,
                user_id=user_id,
                upload_id=upload_id,
                event_type=event_type,
                units=units,
                created_at=created_at,
            )
        entry = self.get_by_id(entry_id)
        if entry is None:
            raise RuntimeError("created usage entry could not be loaded")
        return entry

    def get_by_id(self, entry_id: int) -> UsageLedgerEntry | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, upload_id, event_type, units, created_at
                FROM usage_ledger
                WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
        return _row_to_usage_entry(row)

    def sum_units_for_period(
        self,
        *,
        user_id: int,
        event_type: UsageEventType,
        period_start: datetime,
        period_end: datetime,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        context = nullcontext(conn) if conn is not None else self.db.connect()
        with context as active_conn:
            row = active_conn.execute(
                """
                SELECT COALESCE(SUM(units), 0) AS total_units
                FROM usage_ledger
                WHERE user_id = ?
                  AND event_type = ?
                  AND created_at >= ?
                  AND created_at < ?
                """,
                (
                    user_id,
                    event_type.value,
                    period_start.isoformat(),
                    period_end.isoformat(),
                ),
            ).fetchone()
        if row is None:
            return 0
        return int(row["total_units"] or 0)


def _row_to_usage_entry(row) -> UsageLedgerEntry | None:
    if row is None:
        return None
    return UsageLedgerEntry(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        upload_id=int(row["upload_id"]) if row["upload_id"] is not None else None,
        event_type=UsageEventType(row["event_type"]),
        units=int(row["units"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
