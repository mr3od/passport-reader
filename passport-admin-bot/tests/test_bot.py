from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from passport_admin_bot.bot import admin_command, broadcast_command, recent_command, stats_command
from passport_platform import MonthlyUsageReport, PlanName
from passport_platform.enums import UploadStatus, UserStatus
from passport_platform.schemas.results import RecentUploadRecord
from telegram import Update
from telegram.ext import ContextTypes


class FakeReplyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.markups: list[object] = []

    async def reply_text(self, text: str, **kwargs: object) -> None:
        self.replies.append(text)
        if "reply_markup" in kwargs:
            self.markups.append(kwargs["reply_markup"])


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


def _admin_context(*, services: object, args: list[str] | None = None, is_admin: bool = True):
    settings = SimpleNamespace(
        admin_user_id_set={552002791} if is_admin else set(),
        admin_username_set={"admin"} if is_admin else set(),
    )
    return cast(
        ContextTypes.DEFAULT_TYPE,
        SimpleNamespace(
            args=args or [],
            application=SimpleNamespace(bot_data={"services": services, "settings": settings}),
        ),
    )


def _admin_update(reply: FakeReplyMessage, *, user_id: int = 552002791) -> Update:
    return cast(
        Update,
        SimpleNamespace(
            effective_chat=SimpleNamespace(id=user_id, type="private"),
            effective_user=SimpleNamespace(id=user_id, username="admin"),
            effective_message=reply,
        ),
    )


def test_admin_command_returns_help_for_allowlisted_admin():
    reply = FakeReplyMessage()
    context = _admin_context(services=SimpleNamespace())
    update = _admin_update(reply)

    asyncio.run(admin_command(update, context))

    assert len(reply.replies) == 1
    assert "Admin Panel" in reply.replies[0]
    assert len(reply.markups) == 1


def test_stats_command_rejects_non_admin_user():
    reply = FakeReplyMessage()
    context = _admin_context(services=SimpleNamespace(), is_admin=False)
    update = _admin_update(reply, user_id=12345)

    asyncio.run(stats_command(update, context))

    assert len(reply.replies) == 1
    assert "admin" in reply.replies[0].lower()


def test_recent_command_formats_recent_uploads_for_admin():
    reply = FakeReplyMessage()
    services = SimpleNamespace(
        reporting=SimpleNamespace(
            list_recent_uploads=lambda limit=10: [
                RecentUploadRecord(
                    upload_id=1,
                    user_id=2,
                    external_provider="telegram",
                    external_user_id="12345",
                    display_name="Agency A",
                    plan=PlanName.BASIC,
                    user_status=UserStatus.ACTIVE,
                    filename="passport.jpg",
                    source_ref="telegram://1",
                    upload_status=UploadStatus.PROCESSED,
                    passport_number="A123",
                    error_code=None,
                    created_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
                    completed_at=None,
                )
            ]
        )
    )
    context = _admin_context(services=services, args=["1"])
    update = _admin_update(reply)

    asyncio.run(recent_command(update, context))

    assert len(reply.replies) == 1
    assert "passport.jpg" in reply.replies[0]
    assert "12345" in reply.replies[0]


def test_stats_command_formats_monthly_usage_report():
    reply = FakeReplyMessage()
    services = SimpleNamespace(
        reporting=SimpleNamespace(
            get_monthly_usage_report=lambda: MonthlyUsageReport(
                period_start=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
                total_users=12,
                active_users=11,
                blocked_users=1,
                total_uploads=100,
                total_successes=90,
                total_failures=10,
            )
        )
    )
    context = _admin_context(services=services)
    update = _admin_update(reply)

    asyncio.run(stats_command(update, context))

    assert len(reply.replies) == 1
    assert "Total users: 12" in reply.replies[0]


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
