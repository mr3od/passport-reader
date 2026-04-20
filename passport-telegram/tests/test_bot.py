from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from passport_platform import BroadcastContentType, IssuedTempToken
from passport_platform.enums import UserStatus
from passport_platform.models.auth import TempToken
from passport_telegram.bot import (
    BotServices,
    TelegramImageUpload,
    deliver_pending_broadcast,
    me_command,
    token_command,
)
from passport_telegram.queue import ChatQueue, ChatQueueManager, ItemState, QueueItem
from telegram import Update
from telegram.ext import ContextTypes


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []
        self.photos: list[tuple[int, bytes, str, str | None]] = []
        self._message_counter = 1000

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None):
        self.messages.append((chat_id, text))
        msg = SimpleNamespace(message_id=self._message_counter)
        self._message_counter += 1
        return msg

    async def send_photo(
        self,
        *,
        chat_id: int,
        photo: bytes,
        caption: str,
        parse_mode: str | None = None,
    ) -> None:
        self.photos.append((chat_id, photo, caption, parse_mode))

    async def edit_message_text(self, *, chat_id, message_id, text, reply_markup=None):
        self.messages.append((chat_id, text))

    async def get_file(self, file_id):
        return SimpleNamespace(download_as_bytearray=lambda: b"image-bytes")


class BroadcastAwareBot(FakeBot):
    async def send_photo(
        self,
        *,
        chat_id: int,
        photo,
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> None:
        payload = photo.read() if hasattr(photo, "read") else photo
        self.photos.append((chat_id, payload, caption or "", parse_mode))


class FakeReplyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.parse_modes: list[str | None] = []

    async def reply_text(self, text: str, parse_mode: str | None = None) -> None:
        self.replies.append(text)
        self.parse_modes.append(parse_mode)


def _agency_context(*, services: object, args: list[str] | None = None):
    return cast(
        ContextTypes.DEFAULT_TYPE,
        SimpleNamespace(
            args=args or [],
            application=SimpleNamespace(bot_data={"services": services}),
        ),
    )


def _agency_update(reply: FakeReplyMessage) -> Update:
    return cast(
        Update,
        SimpleNamespace(
            effective_chat=SimpleNamespace(id=1),
            effective_user=SimpleNamespace(
                id=12345, first_name="Agency", last_name="A", username=None
            ),
            effective_message=reply,
        ),
    )


class FakeProcessingService:
    def __init__(self) -> None:
        self.calls = 0
        self.source_refs: list[str] = []

    def process_bytes(self, command):
        self.calls += 1
        self.source_refs.append(command.source_ref)
        return SimpleNamespace(
            is_complete=True,
            is_passport=True,
            extracted_data=SimpleNamespace(full_name_ar="اسم", full_name_en=None),
            filename=command.filename,
        )


def test_token_command_issues_single_use_token_text():
    reply = FakeReplyMessage()
    services = SimpleNamespace(
        users=SimpleNamespace(
            get_or_create_user=lambda command: SimpleNamespace(
                id=1,
                external_user_id="12345",
                status=UserStatus.ACTIVE,
            )
        ),
        auth=SimpleNamespace(
            issue_temp_token=lambda user_id: IssuedTempToken(
                token="tmp-token",
                expires_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
                record=TempToken(
                    id=1,
                    user_id=user_id,
                    token_hash="hash",
                    expires_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
                    used_at=None,
                    created_at=datetime(2026, 3, 13, 11, 0, tzinfo=UTC),
                ),
            )
        ),
    )
    context = _agency_context(services=services)
    update = _agency_update(reply)

    asyncio.run(token_command(update, context))

    assert len(reply.replies) == 1
    assert "`tmp-token`" in reply.replies[0]
    assert "مرة واحدة" in reply.replies[0]
    assert reply.parse_modes == ["Markdown"]


def test_me_command_returns_user_usage_summary():
    reply = FakeReplyMessage()
    report = SimpleNamespace(
        user=SimpleNamespace(
            display_name="Agency A",
            external_user_id="12345",
            plan=SimpleNamespace(value="free"),
            status=SimpleNamespace(value="active"),
        ),
        upload_count=2,
        success_count=1,
        failure_count=1,
        quota_decision=SimpleNamespace(remaining_uploads=18, remaining_successes=19),
    )
    services = SimpleNamespace(
        users=SimpleNamespace(
            get_or_create_user=lambda command: SimpleNamespace(
                id=1,
                external_user_id="12345",
                status=UserStatus.ACTIVE,
            )
        ),
        reporting=SimpleNamespace(get_user_usage_report=lambda user_id: report),
    )
    context = _agency_context(services=services)
    update = _agency_update(reply)

    asyncio.run(me_command(update, context))

    assert len(reply.replies) == 1
    assert "Agency A" in reply.replies[0]
    assert "12345" in reply.replies[0]
    assert "18" in reply.replies[0]


def test_queue_enqueue_starts_worker_and_processes_items():
    """Queue manager processes enqueued uploads serially via a worker."""
    bot = FakeBot()
    processing = FakeProcessingService()
    services = SimpleNamespace(
        users=SimpleNamespace(
            get_or_create_user=lambda command: SimpleNamespace(id=1, status=UserStatus.ACTIVE)
        ),
        processing=processing,
    )
    context = SimpleNamespace(
        bot=bot,
        application=SimpleNamespace(
            bot_data={"services": services},
        ),
    )

    uploads = [
        TelegramImageUpload(
            file_id=f"file-{i}",
            filename=f"passport-{i}.jpg",
            mime_type="image/jpeg",
            source_ref=f"telegram://chat/1/message/2/file/{i}",
            external_message_id=str(i),
            external_file_id=f"file-{i}",
        )
        for i in range(3)
    ]

    async def run():
        manager = ChatQueueManager(
            chat_message_interval=0.0,
            max_concurrent_extractions=4,
            queue_idle_cleanup_seconds=300.0,
        )
        with patch("passport_telegram.bot._download_upload", return_value=b"image-bytes"):
            queue = manager.enqueue(
                context=context,
                chat_id=1,
                external_user_id="12345",
                display_name="Agency A",
                uploads=uploads,
            )
            # Wait for worker to finish.
            assert queue._worker_task is not None
            await queue._worker_task

        return queue

    queue = asyncio.run(run())

    assert processing.calls == 3
    assert processing.source_refs == [u.source_ref for u in uploads]
    assert queue.success_count == 3
    assert queue.fail_count == 0
    assert queue.is_complete


def test_queue_appends_to_existing_queue():
    """New uploads arriving while worker is running get appended."""
    queue = ChatQueue(chat_id=1, external_user_id="12345")
    upload = TelegramImageUpload(
        file_id="f1",
        filename="p1.jpg",
        mime_type="image/jpeg",
        source_ref="ref1",
        external_message_id="1",
        external_file_id="f1",
    )
    queue.items.append(QueueItem(upload=upload, state=ItemState.SUCCESS, display_name="Test"))

    assert queue.total == 1
    assert queue.success_count == 1

    upload2 = TelegramImageUpload(
        file_id="f2",
        filename="p2.jpg",
        mime_type="image/jpeg",
        source_ref="ref2",
        external_message_id="2",
        external_file_id="f2",
    )
    queue.items.append(QueueItem(upload=upload2))

    assert queue.total == 2
    assert queue.pending_count == 1
    assert not queue.is_complete


def _make_upload(fid: str) -> TelegramImageUpload:
    return TelegramImageUpload(
        file_id=fid,
        filename=f"{fid}.jpg",
        mime_type="image/jpeg",
        source_ref=f"ref-{fid}",
        external_message_id="1",
        external_file_id=fid,
    )


def test_chat_queue_counts():
    """ChatQueue properties compute correct counts."""
    queue = ChatQueue(chat_id=1, external_user_id="u1")
    queue.items = [
        QueueItem(upload=_make_upload("a"), state=ItemState.SUCCESS, display_name="A"),
        QueueItem(upload=_make_upload("b"), state=ItemState.FAILED, failure_reason="err"),
        QueueItem(upload=_make_upload("c"), state=ItemState.PENDING),
    ]
    queue.delivered_count = 1

    assert queue.total == 3
    assert queue.success_count == 1
    assert queue.fail_count == 1
    assert queue.pending_count == 1
    assert queue.done_count == 2
    assert queue.undelivered_success_count == 0
    assert not queue.is_complete


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

    asyncio.run(deliver_pending_broadcast(bot=bot, services=cast(BotServices, services)))

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

    asyncio.run(deliver_pending_broadcast(bot=bot, services=cast(BotServices, services)))

    assert bot.photos[0][0] == 100
    assert bot.photos[0][1] == b"image"
    assert bot.photos[0][2] == "Read this"
