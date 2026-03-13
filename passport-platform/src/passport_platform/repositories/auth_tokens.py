from __future__ import annotations

import sqlite3
from contextlib import nullcontext
from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.models.auth import ExtensionSession, TempToken


class AuthTokensRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_temp_token(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        conn: sqlite3.Connection | None = None,
    ) -> TempToken:
        created_at = datetime.now(UTC)
        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as active_conn:
            cursor = active_conn.execute(
                """
                INSERT INTO temp_tokens (user_id, token_hash, expires_at, used_at, created_at)
                VALUES (?, ?, ?, NULL, ?)
                """,
                (
                    user_id,
                    token_hash,
                    expires_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
            token_id = int(cursor.lastrowid)
        if conn is not None:
            return TempToken(
                id=token_id,
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
                used_at=None,
                created_at=created_at,
            )
        token = self.get_temp_token_by_id(token_id)
        if token is None:
            raise RuntimeError("created temp token could not be loaded")
        return token

    def get_temp_token_by_hash(
        self,
        token_hash: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> TempToken | None:
        context = nullcontext(conn) if conn is not None else self.db.connect()
        with context as active_conn:
            row = active_conn.execute(
                """
                SELECT id, user_id, token_hash, expires_at, used_at, created_at
                FROM temp_tokens
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        return _row_to_temp_token(row)

    def get_temp_token_by_id(self, token_id: int) -> TempToken | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, token_hash, expires_at, used_at, created_at
                FROM temp_tokens
                WHERE id = ?
                """,
                (token_id,),
            ).fetchone()
        return _row_to_temp_token(row)

    def get_temp_token_by_id_for_update(
        self,
        token_id: int,
        *,
        conn: sqlite3.Connection,
    ) -> TempToken | None:
        row = conn.execute(
            """
            SELECT id, user_id, token_hash, expires_at, used_at, created_at
            FROM temp_tokens
            WHERE id = ?
            """,
            (token_id,),
        ).fetchone()
        return _row_to_temp_token(row)

    def mark_temp_token_used(
        self,
        token_id: int,
        *,
        used_at: datetime,
        conn: sqlite3.Connection | None = None,
    ) -> TempToken:
        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as active_conn:
            active_conn.execute(
                "UPDATE temp_tokens SET used_at = ? WHERE id = ?",
                (used_at.isoformat(), token_id),
            )
        token = (
            self.get_temp_token_by_id_for_update(token_id, conn=active_conn)
            if conn is not None
            else self.get_temp_token_by_id(token_id)
        )
        if token is None:
            raise KeyError(f"temp token {token_id} not found")
        return token

    def create_extension_session(
        self,
        *,
        user_id: int,
        session_token_hash: str,
        expires_at: datetime,
        conn: sqlite3.Connection | None = None,
    ) -> ExtensionSession:
        created_at = datetime.now(UTC)
        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as active_conn:
            cursor = active_conn.execute(
                """
                INSERT INTO extension_sessions (
                    user_id,
                    session_token_hash,
                    expires_at,
                    revoked_at,
                    created_at
                )
                VALUES (?, ?, ?, NULL, ?)
                """,
                (
                    user_id,
                    session_token_hash,
                    expires_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
            session_id = int(cursor.lastrowid)
        if conn is not None:
            return ExtensionSession(
                id=session_id,
                user_id=user_id,
                session_token_hash=session_token_hash,
                expires_at=expires_at,
                revoked_at=None,
                created_at=created_at,
            )
        session = self.get_extension_session_by_id(session_id)
        if session is None:
            raise RuntimeError("created extension session could not be loaded")
        return session

    def get_extension_session_by_hash(self, session_token_hash: str) -> ExtensionSession | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    user_id,
                    session_token_hash,
                    expires_at,
                    revoked_at,
                    created_at
                FROM extension_sessions
                WHERE session_token_hash = ?
                """,
                (session_token_hash,),
            ).fetchone()
        return _row_to_extension_session(row)

    def get_extension_session_by_id(self, session_id: int) -> ExtensionSession | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    user_id,
                    session_token_hash,
                    expires_at,
                    revoked_at,
                    created_at
                FROM extension_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        return _row_to_extension_session(row)

    def revoke_extension_session(
        self,
        session_id: int,
        *,
        revoked_at: datetime,
        conn: sqlite3.Connection | None = None,
    ) -> ExtensionSession:
        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as active_conn:
            active_conn.execute(
                "UPDATE extension_sessions SET revoked_at = ? WHERE id = ?",
                (revoked_at.isoformat(), session_id),
            )
        session = self.get_extension_session_by_id(session_id)
        if session is None:
            raise KeyError(f"extension session {session_id} not found")
        return session


def _row_to_temp_token(row) -> TempToken | None:
    if row is None:
        return None
    return TempToken(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        token_hash=row["token_hash"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
        used_at=datetime.fromisoformat(row["used_at"]) if row["used_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_extension_session(row) -> ExtensionSession | None:
    if row is None:
        return None
    return ExtensionSession(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        session_token_hash=row["session_token_hash"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
        revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )
