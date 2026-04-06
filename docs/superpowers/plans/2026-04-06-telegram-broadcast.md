# Telegram Broadcast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins queue a text message or photo-with-caption broadcast that the agency bot delivers to all active Telegram users.

**Architecture:** The admin bot remains the command entrypoint, but it does not deliver messages. Instead, `passport-platform` owns a durable broadcast queue plus artifact storage for admin-uploaded photos, and the agency bot runs a small worker that claims pending broadcasts and fans them out through the bot token agencies already started.

**Tech Stack:** Python 3.12, SQLite, python-telegram-bot, `passport-platform` services/repositories/models, local artifact storage, pytest, ruff, ty

---

## File Map

Platform storage and schema:
- Modify: `passport-platform/src/passport_platform/db.py`
- Create: `passport-platform/migrations/0003_broadcasts.sql`

Platform domain model and API:
- Create: `passport-platform/src/passport_platform/models/broadcast.py`
- Modify: `passport-platform/src/passport_platform/models/__init__.py`
- Create: `passport-platform/src/passport_platform/repositories/broadcasts.py`
- Modify: `passport-platform/src/passport_platform/repositories/users.py`
- Create: `passport-platform/src/passport_platform/services/broadcasts.py`
- Modify: `passport-platform/src/passport_platform/services/users.py`
- Modify: `passport-platform/src/passport_platform/services/__init__.py`
- Modify: `passport-platform/src/passport_platform/factory.py`
- Modify: `passport-platform/src/passport_platform/__init__.py`

Platform tests:
- Create: `passport-platform/tests/test_broadcast_service.py`
- Modify: `passport-platform/tests/test_user_service.py`

Admin bot:
- Modify: `passport-admin-bot/src/passport_admin_bot/bot.py`
- Modify: `passport-admin-bot/src/passport_admin_bot/messages.py`
- Modify: `passport-admin-bot/tests/test_bot.py`
- Modify: `passport-admin-bot/README.md`

Agency bot:
- Modify: `passport-telegram/src/passport_telegram/bot.py`
- Modify: `passport-telegram/tests/test_bot.py`

## Task 1: Add Broadcast Storage And Domain Types

**Files:**
- Create: `passport-platform/src/passport_platform/models/broadcast.py`
- Modify: `passport-platform/src/passport_platform/models/__init__.py`
- Modify: `passport-platform/src/passport_platform/db.py`
- Create: `passport-platform/migrations/0003_broadcasts.sql`

- [ ] **Step 1: Write the failing platform storage test**

Add this new test file:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest passport-platform/tests/test_broadcast_service.py::test_database_initializes_broadcasts_table -q
```

Expected: `FAIL` because the `broadcasts` table does not exist yet.

- [ ] **Step 3: Add the broadcast model and schema**

Create `passport-platform/src/passport_platform/models/broadcast.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BroadcastContentType(StrEnum):
    TEXT = "text"
    PHOTO = "photo"


class BroadcastStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class Broadcast:
    id: int
    created_by_external_user_id: str
    content_type: BroadcastContentType
    text_body: str | None
    caption: str | None
    artifact_path: str | None
    status: BroadcastStatus
    total_targets: int
    sent_count: int
    failed_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
```

Update `passport-platform/src/passport_platform/models/__init__.py`:

```python
from passport_platform.models.broadcast import Broadcast, BroadcastContentType, BroadcastStatus
from passport_platform.models.auth import ExtensionSession, TempToken
from passport_platform.models.plan import PlanPolicy
from passport_platform.models.processing import RecordedProcessing
from passport_platform.models.upload import ProcessingResult, Upload
from passport_platform.models.usage import UsageLedgerEntry, UsageSummary
from passport_platform.models.user import User

__all__ = [
    "Broadcast",
    "BroadcastContentType",
    "BroadcastStatus",
    "ExtensionSession",
    "PlanPolicy",
    "ProcessingResult",
    "RecordedProcessing",
    "Upload",
    "TempToken",
    "UsageLedgerEntry",
    "UsageSummary",
    "User",
]
```

Update `passport-platform/src/passport_platform/db.py` `SCHEMA_SQL` and `_upgrade_schema()` to add the table:

```python
CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by_external_user_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    text_body TEXT,
    caption TEXT,
    artifact_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    total_targets INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
```

Add indexes in `INDEX_SQL`:

```python
CREATE INDEX IF NOT EXISTS idx_broadcasts_status_created_at
    ON broadcasts (status, created_at, id);
```

Add `_upgrade_schema()` support:

```python
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by_external_user_id TEXT NOT NULL,
                content_type TEXT NOT NULL,
                text_body TEXT,
                caption TEXT,
                artifact_path TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                total_targets INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_broadcasts_status_created_at "
            "ON broadcasts (status, created_at, id)"
        )
```

Create `passport-platform/migrations/0003_broadcasts.sql`:

```sql
CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by_external_user_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    text_body TEXT,
    caption TEXT,
    artifact_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    total_targets INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_broadcasts_status_created_at
    ON broadcasts (status, created_at, id);
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest passport-platform/tests/test_broadcast_service.py::test_database_initializes_broadcasts_table -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add passport-platform/src/passport_platform/models/broadcast.py passport-platform/src/passport_platform/models/__init__.py passport-platform/src/passport_platform/db.py passport-platform/migrations/0003_broadcasts.sql passport-platform/tests/test_broadcast_service.py
git commit -m "feat: add broadcast storage model [codex]"
```

## Task 2: Add Broadcast Repository And Service APIs

**Files:**
- Create: `passport-platform/src/passport_platform/repositories/broadcasts.py`
- Modify: `passport-platform/src/passport_platform/repositories/users.py`
- Create: `passport-platform/src/passport_platform/services/broadcasts.py`
- Modify: `passport-platform/src/passport_platform/services/users.py`
- Modify: `passport-platform/src/passport_platform/services/__init__.py`
- Modify: `passport-platform/src/passport_platform/factory.py`
- Modify: `passport-platform/src/passport_platform/__init__.py`
- Create: `passport-platform/tests/test_broadcast_service.py`
- Modify: `passport-platform/tests/test_user_service.py`

- [ ] **Step 1: Write the failing service tests**

Append these tests to `passport-platform/tests/test_broadcast_service.py`:

```python
from __future__ import annotations

from passport_platform.db import Database
from passport_platform.enums import ExternalProvider, PlanName, UserStatus
from passport_platform.repositories.broadcasts import BroadcastsRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.services.broadcasts import BroadcastService
from passport_platform.services.users import UserService
from passport_platform.storage import LocalArtifactStore


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
```

Add this test to `passport-platform/tests/test_user_service.py`:

```python
def test_list_active_users_by_provider_filters_blocked_and_other_providers(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UsersRepository(db)
    service = UserService(users)
    users.create(
        external_provider=ExternalProvider.TELEGRAM,
        external_user_id="100",
        display_name="Agency A",
        plan=PlanName.FREE,
        status=UserStatus.ACTIVE,
    )
    users.create(
        external_provider=ExternalProvider.TELEGRAM,
        external_user_id="200",
        display_name="Agency B",
        plan=PlanName.FREE,
        status=UserStatus.BLOCKED,
    )
    users.create(
        external_provider=ExternalProvider.API,
        external_user_id="300",
        display_name="API User",
        plan=PlanName.FREE,
        status=UserStatus.ACTIVE,
    )

    active = service.list_active_users_by_provider(ExternalProvider.TELEGRAM)

    assert [user.external_user_id for user in active] == ["100"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest passport-platform/tests/test_broadcast_service.py passport-platform/tests/test_user_service.py -q
```

Expected: `FAIL` with missing repository/service methods and missing provider filter support.

- [ ] **Step 3: Implement the repository and service layer**

Create `passport-platform/src/passport_platform/repositories/broadcasts.py`:

```python
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
                SET status = ?, sent_count = ?, failed_count = ?, completed_at = ?, error_message = NULL
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
```

Update `passport-platform/src/passport_platform/repositories/users.py`:

```python
    def list_active_by_provider(self, external_provider: ExternalProvider) -> list[User]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    external_provider,
                    external_user_id,
                    display_name,
                    plan,
                    status,
                    created_at
                FROM users
                WHERE external_provider = ? AND status = ?
                ORDER BY created_at ASC, id ASC
                """,
                (external_provider.value, UserStatus.ACTIVE.value),
            ).fetchall()
        return [user for row in rows if (user := _row_to_user(row)) is not None]
```

Create `passport-platform/src/passport_platform/services/broadcasts.py`:

```python
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

    def create_text_broadcast(self, *, created_by_external_user_id: str, text_body: str) -> Broadcast:
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
        total_targets = len(
            self.users.list_active_users_by_provider(ExternalProvider.TELEGRAM)
        )
        return self.broadcasts.claim_next_pending(total_targets=total_targets)

    def mark_completed(self, broadcast_id: int, *, sent_count: int, failed_count: int) -> Broadcast:
        return self.broadcasts.mark_completed(
            broadcast_id,
            sent_count=sent_count,
            failed_count=failed_count,
        )

    def mark_failed(self, broadcast_id: int, *, error_message: str) -> Broadcast:
        return self.broadcasts.mark_failed(broadcast_id, error_message=error_message)
```

Update `passport-platform/src/passport_platform/services/users.py`:

```python
    def list_active_users_by_provider(
        self,
        external_provider: ExternalProvider,
    ) -> list[User]:
        return self.users.list_active_by_provider(external_provider)
```

Update `passport-platform/src/passport_platform/services/__init__.py`:

```python
from passport_platform.services.auth import AuthService
from passport_platform.services.broadcasts import BroadcastService
from passport_platform.services.processing import ProcessingService
from passport_platform.services.quotas import QuotaService
from passport_platform.services.records import RecordsService
from passport_platform.services.reporting import ReportingService
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService

__all__ = [
    "AuthService",
    "BroadcastService",
    "ProcessingService",
    "QuotaService",
    "RecordsService",
    "ReportingService",
    "UploadService",
    "UserService",
]
```

Update `passport-platform/src/passport_platform/factory.py`:

```python
from passport_platform.repositories.broadcasts import BroadcastsRepository
from passport_platform.services.broadcasts import BroadcastService

@dataclass(slots=True)
class PlatformRuntime:
    ...
    broadcasts: BroadcastService

...
    return PlatformRuntime(
        settings=settings,
        db=db,
        artifacts=LocalArtifactStore(settings.artifacts_dir),
        users=users,
        auth=AuthService(AuthTokensRepository(db), users),
        quotas=quotas,
        uploads=uploads,
        records=RecordsService(RecordsRepository(db)),
        reporting=ReportingService(
            users=users,
            quotas=quotas,
            reporting=ReportingRepository(db),
        ),
        broadcasts=BroadcastService(
            broadcasts=BroadcastsRepository(db),
            users=users,
            artifacts=LocalArtifactStore(settings.artifacts_dir),
        ),
    )
```

Update `passport-platform/src/passport_platform/__init__.py`:

```python
from passport_platform.models.broadcast import Broadcast, BroadcastContentType, BroadcastStatus
from passport_platform.services.broadcasts import BroadcastService

__all__ = [
    ...
    "Broadcast",
    "BroadcastContentType",
    "BroadcastService",
    "BroadcastStatus",
    ...
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest passport-platform/tests/test_broadcast_service.py passport-platform/tests/test_user_service.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add passport-platform/src/passport_platform/repositories/broadcasts.py passport-platform/src/passport_platform/repositories/users.py passport-platform/src/passport_platform/services/broadcasts.py passport-platform/src/passport_platform/services/users.py passport-platform/src/passport_platform/services/__init__.py passport-platform/src/passport_platform/factory.py passport-platform/src/passport_platform/__init__.py passport-platform/tests/test_broadcast_service.py passport-platform/tests/test_user_service.py
git commit -m "feat: add broadcast service workflow [codex]"
```

## Task 3: Add Admin `/broadcast` Command

**Files:**
- Modify: `passport-admin-bot/src/passport_admin_bot/bot.py`
- Modify: `passport-admin-bot/src/passport_admin_bot/messages.py`
- Modify: `passport-admin-bot/tests/test_bot.py`
- Modify: `passport-admin-bot/README.md`

- [ ] **Step 1: Write the failing admin bot tests**

Append these tests to `passport-admin-bot/tests/test_bot.py`:

```python
from passport_admin_bot.bot import broadcast_command


class FakeTelegramFile:
    def __init__(self, data: bytes) -> None:
        self.data = data

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self.data)


class FakePhoto:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


class FakeBot:
    def __init__(self, data: bytes = b"photo-bytes") -> None:
        self.data = data

    async def get_file(self, file_id: str) -> FakeTelegramFile:
        return FakeTelegramFile(self.data)


def test_broadcast_command_queues_text_for_admin():
    reply = FakeReplyMessage()
    queued = []
    services = SimpleNamespace(
        broadcasts=SimpleNamespace(
            create_text_broadcast=lambda **kwargs: queued.append(kwargs) or SimpleNamespace(id=1)
        )
    )
    context = _admin_context(services=services, args=["System", "maintenance"])
    context.bot = FakeBot()
    update = _admin_update(reply)

    asyncio.run(broadcast_command(update, context))

    assert queued == [
        {
            "created_by_external_user_id": "552002791",
            "text_body": "System maintenance",
        }
    ]
    assert "queued" in reply.replies[0].lower()


def test_broadcast_command_queues_photo_reply_for_admin():
    reply = FakeReplyMessage()
    queued = []
    services = SimpleNamespace(
        broadcasts=SimpleNamespace(
            create_photo_broadcast=lambda **kwargs: queued.append(kwargs) or SimpleNamespace(id=1)
        )
    )
    context = _admin_context(services=services)
    context.bot = FakeBot(data=b"image")
    update = cast(
        Update,
        SimpleNamespace(
            effective_chat=SimpleNamespace(id=552002791, type="private"),
            effective_user=SimpleNamespace(id=552002791, username="admin"),
            effective_message=reply,
            message=SimpleNamespace(
                reply_to_message=SimpleNamespace(
                    photo=[FakePhoto("small"), FakePhoto("largest")],
                    caption="Read this",
                )
            ),
        ),
    )

    asyncio.run(broadcast_command(update, context))

    assert queued[0]["created_by_external_user_id"] == "552002791"
    assert queued[0]["photo_bytes"] == b"image"
    assert queued[0]["caption"] == "Read this"
    assert queued[0]["filename"] == "broadcast.jpg"


def test_broadcast_command_returns_usage_when_empty():
    reply = FakeReplyMessage()
    context = _admin_context(services=SimpleNamespace(), args=[])
    context.bot = FakeBot()
    update = _admin_update(reply)

    asyncio.run(broadcast_command(update, context))

    assert "broadcast" in reply.replies[0].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest passport-admin-bot/tests/test_bot.py -q
```

Expected: `FAIL` because `/broadcast` does not exist yet.

- [ ] **Step 3: Implement the admin command**

Update `passport-admin-bot/src/passport_admin_bot/messages.py`:

```python
def help_text() -> str:
    return (
        "Admin commands:\n"
        "/admin - show admin commands\n"
        "/stats - monthly usage summary\n"
        "/recent [count] - recent uploads\n"
        "/usage <telegram_user_id> - usage for one agency\n"
        "/setplan <telegram_user_id> <free|basic|pro> - change plan\n"
        "/block <telegram_user_id> - block agency access\n"
        "/unblock <telegram_user_id> - restore agency access\n"
        "/broadcast <message> - queue a text broadcast\n"
        "/broadcast - reply to a photo to queue a photo broadcast"
    )


def broadcast_help_text() -> str:
    return (
        "Usage:\n"
        "/broadcast <message>\n"
        "or reply to a photo with /broadcast"
    )


def broadcast_queued_text() -> str:
    return "Broadcast queued successfully."


def broadcast_download_failed_text() -> str:
    return "Could not download the photo for broadcast."
```

Update `passport-admin-bot/src/passport_admin_bot/bot.py`:

```python
from telegram import Message, PhotoSize, Update

from passport_admin_bot.messages import (
    admin_only_text,
    broadcast_download_failed_text,
    broadcast_help_text,
    broadcast_queued_text,
    ...
)


@dataclass(slots=True)
class BotServices:
    users: UserService
    reporting: ReportingService
    broadcasts: BroadcastService
```

Extend `_build_bot_services()`:

```python
    return BotServices(
        users=platform_runtime.users,
        reporting=platform_runtime.reporting,
        broadcasts=platform_runtime.broadcasts,
    )
```

Register the handler:

```python
    application.add_handler(CommandHandler("broadcast", broadcast_command))
```

Add the command:

```python
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_admin(update, context):
        return
    services: BotServices = context.application.bot_data["services"]
    admin_user = update.effective_user
    if admin_user is None:
        await _reply_text(update, broadcast_help_text())
        return

    message_text = " ".join(context.args or []).strip()
    if message_text:
        services.broadcasts.create_text_broadcast(
            created_by_external_user_id=str(admin_user.id),
            text_body=message_text,
        )
        await _reply_text(update, broadcast_queued_text())
        return

    reply_to_message = update.message.reply_to_message if update.message else None
    photo = _largest_photo(reply_to_message)
    if photo is None:
        await _reply_text(update, broadcast_help_text())
        return

    telegram_file = await context.bot.get_file(photo.file_id)
    try:
        photo_bytes = bytes(await telegram_file.download_as_bytearray())
    except Exception:
        await _reply_text(update, broadcast_download_failed_text())
        return

    services.broadcasts.create_photo_broadcast(
        created_by_external_user_id=str(admin_user.id),
        photo_bytes=photo_bytes,
        filename="broadcast.jpg",
        content_type="image/jpeg",
        caption=reply_to_message.caption if reply_to_message else None,
    )
    await _reply_text(update, broadcast_queued_text())


def _largest_photo(message: Message | None) -> PhotoSize | None:
    if message is None or not message.photo:
        return None
    return message.photo[-1]
```

Update `passport-admin-bot/README.md` command list with the new `/broadcast` usage.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest passport-admin-bot/tests/test_bot.py -q
```

Expected: all admin bot tests pass.

- [ ] **Step 5: Commit**

```bash
git add passport-admin-bot/src/passport_admin_bot/bot.py passport-admin-bot/src/passport_admin_bot/messages.py passport-admin-bot/tests/test_bot.py passport-admin-bot/README.md
git commit -m "feat: add admin broadcast command [codex]"
```

## Task 4: Add Agency Bot Broadcast Worker

**Files:**
- Modify: `passport-telegram/src/passport_telegram/bot.py`
- Modify: `passport-telegram/tests/test_bot.py`

- [ ] **Step 1: Write the failing worker tests**

Append these tests to `passport-telegram/tests/test_bot.py`:

```python
from pathlib import Path

from passport_platform import BroadcastContentType
from passport_telegram.bot import deliver_pending_broadcast


class BroadcastAwareBot(FakeBot):
    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))

    async def send_photo(
        self,
        *,
        chat_id: int,
        photo,
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> None:
        payload = photo.read() if hasattr(photo, "read") else photo
        self.photos.append((chat_id, payload, caption, parse_mode))


def test_deliver_pending_broadcast_sends_text_to_active_users(tmp_path) -> None:
    bot = BroadcastAwareBot()
    broadcast = SimpleNamespace(
        id=7,
        content_type=BroadcastContentType.TEXT,
        text_body="Maintenance",
        caption=None,
        artifact_path=None,
    )
    services = SimpleNamespace(
        broadcasts=SimpleNamespace(
            claim_next_pending_broadcast=lambda: broadcast,
            mark_completed=lambda broadcast_id, sent_count, failed_count: SimpleNamespace(),
            mark_failed=lambda broadcast_id, error_message: SimpleNamespace(),
        ),
        users=SimpleNamespace(
            list_active_users_by_provider=lambda provider: [
                SimpleNamespace(external_user_id="100"),
                SimpleNamespace(external_user_id="200"),
            ]
        ),
    )

    asyncio.run(deliver_pending_broadcast(bot=bot, services=services))

    assert bot.messages == [(100, "Maintenance"), (200, "Maintenance")]


def test_deliver_pending_broadcast_reuploads_photo_bytes(tmp_path) -> None:
    bot = BroadcastAwareBot()
    artifact = tmp_path / "broadcast.jpg"
    artifact.write_bytes(b"image")
    broadcast = SimpleNamespace(
        id=9,
        content_type=BroadcastContentType.PHOTO,
        text_body=None,
        caption="Read this",
        artifact_path=str(artifact),
    )
    services = SimpleNamespace(
        broadcasts=SimpleNamespace(
            claim_next_pending_broadcast=lambda: broadcast,
            mark_completed=lambda broadcast_id, sent_count, failed_count: SimpleNamespace(),
            mark_failed=lambda broadcast_id, error_message: SimpleNamespace(),
        ),
        users=SimpleNamespace(
            list_active_users_by_provider=lambda provider: [SimpleNamespace(external_user_id="100")]
        ),
    )

    asyncio.run(deliver_pending_broadcast(bot=bot, services=services))

    assert bot.photos[0][0] == 100
    assert bot.photos[0][1] == b"image"
    assert bot.photos[0][2] == "Read this"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest passport-telegram/tests/test_bot.py -q
```

Expected: `FAIL` because there is no broadcast worker.

- [ ] **Step 3: Implement the worker**

Update `passport-telegram/src/passport_telegram/bot.py`:

```python
from pathlib import Path

from passport_platform import (
    AuthService,
    BroadcastContentType,
    BroadcastService,
    ChannelName,
    ExternalProvider,
    ...
)


@dataclass(slots=True)
class BotServices:
    auth: AuthService
    processing: ProcessingService
    users: UserService
    quotas: QuotaService
    reporting: ReportingService
    records: RecordsService
    broadcasts: BroadcastService
```

Extend `_build_bot_services()`:

```python
    return BotServices(
        auth=platform_runtime.auth,
        processing=processing_runtime.processing,
        users=platform_runtime.users,
        quotas=platform_runtime.quotas,
        reporting=platform_runtime.reporting,
        records=platform_runtime.records,
        broadcasts=platform_runtime.broadcasts,
    )
```

Add the worker helpers:

```python
async def deliver_pending_broadcast(*, bot, services: BotServices) -> None:
    broadcast = await asyncio.to_thread(services.broadcasts.claim_next_pending_broadcast)
    if broadcast is None:
        return

    users = await asyncio.to_thread(
        services.users.list_active_users_by_provider,
        ExternalProvider.TELEGRAM,
    )
    sent_count = 0
    failed_count = 0

    try:
        for user in users:
            chat_id = int(user.external_user_id)
            try:
                if broadcast.content_type is BroadcastContentType.TEXT:
                    await bot.send_message(chat_id=chat_id, text=broadcast.text_body or "")
                else:
                    with Path(broadcast.artifact_path or "").open("rb") as photo_file:
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_file,
                            caption=broadcast.caption,
                        )
                sent_count += 1
            except Exception:
                logging.getLogger(__name__).exception(
                    "broadcast_delivery_failed",
                    extra={"broadcast_id": broadcast.id, "external_user_id": user.external_user_id},
                )
                failed_count += 1
    except Exception as exc:
        await asyncio.to_thread(
            services.broadcasts.mark_failed,
            broadcast.id,
            error_message=str(exc),
        )
        return

    await asyncio.to_thread(
        services.broadcasts.mark_completed,
        broadcast.id,
        sent_count=sent_count,
        failed_count=failed_count,
    )


async def broadcast_worker(application: Application) -> None:
    services: BotServices = application.bot_data["services"]
    while True:
        try:
            await deliver_pending_broadcast(bot=application.bot, services=services)
        except Exception:
            logging.getLogger(__name__).exception("broadcast_worker_failed")
        await asyncio.sleep(3)


async def _post_init(application: Application) -> None:
    application.bot_data["broadcast_worker_task"] = asyncio.create_task(broadcast_worker(application))


async def _post_shutdown(application: Application) -> None:
    task = application.bot_data.get("broadcast_worker_task")
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
```

Wire lifecycle in `build_application()`:

```python
    application = (
        Application.builder()
        .token(settings.bot_token.get_secret_value())
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
```

Add the missing import:

```python
import contextlib
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest passport-telegram/tests/test_bot.py -q
```

Expected: all Telegram bot tests pass.

- [ ] **Step 5: Commit**

```bash
git add passport-telegram/src/passport_telegram/bot.py passport-telegram/tests/test_bot.py
git commit -m "feat: add agency broadcast worker [codex]"
```

## Task 5: Verify, Polish, And Document

**Files:**
- Modify: `passport-admin-bot/README.md`
- Modify: `docs/HISTORY.md`

- [ ] **Step 1: Write the history entry**

Append this entry to `docs/HISTORY.md` after implementation is complete:

```markdown
## 2026-04-06

- Added admin-to-agency Telegram broadcast support with queued text and photo notifications, authored by Codex.
```

- [ ] **Step 2: Run formatting and linting**

Run:

```bash
uv run ruff format passport-platform/src passport-platform/tests passport-admin-bot/src passport-admin-bot/tests passport-telegram/src passport-telegram/tests
uv run ruff check passport-platform/src passport-platform/tests passport-admin-bot/src passport-admin-bot/tests passport-telegram/src passport-telegram/tests
```

Expected: formatting completes and `ruff check` reports no errors.

- [ ] **Step 3: Run type checking**

Run:

```bash
uv run ty check passport-platform passport-admin-bot passport-telegram
```

Expected: no type errors.

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest passport-platform/tests/test_broadcast_service.py passport-platform/tests/test_user_service.py passport-admin-bot/tests/test_bot.py passport-telegram/tests/test_bot.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 5: Run boundary checks if imports changed**

Run:

```bash
uv run lint-imports
```

Expected: passes with no contract violations.

- [ ] **Step 6: Commit**

```bash
git add passport-admin-bot/README.md docs/HISTORY.md
git commit -m "docs: record broadcast support [codex]"
```
