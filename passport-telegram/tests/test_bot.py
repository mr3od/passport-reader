from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest
from passport_platform import BroadcastContentType, IssuedTempToken, PlanName, QuotaDecision
from passport_platform.enums import UserStatus
from passport_platform.models.auth import TempToken
from passport_telegram.bot import (
    BotServices,
    InflightLimiter,
    TelegramImageUpload,
    account_command,
    deliver_pending_broadcast,
    plan_command,
    process_upload_batch,
    token_command,
    usage_command,
)
from telegram import Update
from telegram.ext import ContextTypes


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []
        self.photos: list[tuple[int, bytes, str, str | None]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))

    async def send_photo(
        self,
        *,
        chat_id: int,
        photo: bytes,
        caption: str,
        parse_mode: str | None = None,
    ) -> None:
        self.photos.append((chat_id, photo, caption, parse_mode))


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

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


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
        return SimpleNamespace(is_complete=True, extracted_data=None)


class DenyInflightLimiter:
    async def try_acquire(self, external_user_id: str):
        return None


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
    assert "tmp-token" in reply.replies[0]
    assert "مرة واحدة" in reply.replies[0]


def test_account_command_returns_user_usage_summary():
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

    asyncio.run(account_command(update, context))

    assert len(reply.replies) == 1
    assert "Agency A" in reply.replies[0]
    assert "12345" in reply.replies[0]
    assert "18" in reply.replies[0]


def test_usage_command_returns_self_usage_without_admin_args():
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
    context = _agency_context(services=services, args=[])
    update = _agency_update(reply)

    asyncio.run(usage_command(update, context))

    assert len(reply.replies) == 1
    assert "Agency A" in reply.replies[0]
    assert "18" in reply.replies[0]


def test_usage_command_with_args_returns_self_only_help_text():
    reply = FakeReplyMessage()
    services = SimpleNamespace(
        users=SimpleNamespace(
            get_or_create_user=lambda command: SimpleNamespace(
                id=1,
                external_user_id="12345",
                status=UserStatus.ACTIVE,
            )
        ),
        reporting=SimpleNamespace(get_user_usage_report=lambda user_id: None),
    )
    context = _agency_context(services=services, args=["999"])
    update = _agency_update(reply)

    asyncio.run(usage_command(update, context))

    assert len(reply.replies) == 1
    assert "/usage" in reply.replies[0]
    assert "<telegram_user_id>" not in reply.replies[0]


def test_plan_command_returns_short_user_plan_summary():
    reply = FakeReplyMessage()
    services = SimpleNamespace(
        users=SimpleNamespace(
            get_or_create_user=lambda command: SimpleNamespace(
                id=1,
                display_name="Agency A",
                external_user_id="12345",
                plan=SimpleNamespace(value="pro"),
                status=SimpleNamespace(value="active"),
            )
        )
    )
    context = _agency_context(services=services)
    update = _agency_update(reply)

    asyncio.run(plan_command(update, context))

    assert len(reply.replies) == 1
    assert "Agency A" in reply.replies[0]
    assert "pro" in reply.replies[0]
    assert "active" in reply.replies[0]


def test_process_upload_batch_splits_batches_above_plan_limit():
    bot = FakeBot()
    processing = FakeProcessingService()
    services = SimpleNamespace(
        users=SimpleNamespace(
            get_or_create_user=lambda command: SimpleNamespace(id=1, status=UserStatus.ACTIVE)
        ),
        quotas=SimpleNamespace(
            evaluate_user_quota=lambda user: QuotaDecision(
                allowed=True,
                plan=PlanName.FREE,
                monthly_upload_limit=20,
                monthly_uploads_used=0,
                monthly_success_limit=20,
                monthly_successes_used=0,
                remaining_uploads=20,
                remaining_successes=20,
                max_batch_size=2,
            )
        ),
        processing=processing,
    )
    context = SimpleNamespace(
        bot=bot,
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(max_images_per_batch=10),
                "services": services,
            }
        ),
    )
    uploads = [
        TelegramImageUpload(
            file_id=f"file-{index}",
            filename=f"passport-{index}.jpg",
            mime_type="image/jpeg",
            source_ref=f"telegram://chat/1/message/2/file/{index}",
            external_message_id=str(index),
            external_file_id=f"file-{index}",
        )
        for index in range(3)
    ]

    with patch("passport_telegram.bot._download_upload", return_value=b"image-bytes"):
        asyncio.run(
            process_upload_batch(
                context=context,
                chat_id=1,
                external_user_id="12345",
                display_name="Agency A",
                uploads=uploads,
            )
        )

    assert processing.calls == 3
    assert processing.source_refs == [upload.source_ref for upload in uploads]
    assert len(bot.photos) == 3
    assert all(photo[3] == "Markdown" for photo in bot.photos)
    assert len(bot.messages) == 1
    assert "2" in bot.messages[0][1]


def test_process_upload_batch_returns_busy_when_limiter_is_exhausted():
    bot = FakeBot()
    processing = FakeProcessingService()
    services = SimpleNamespace(
        users=SimpleNamespace(
            get_or_create_user=lambda command: SimpleNamespace(id=1, status=UserStatus.ACTIVE)
        ),
        quotas=SimpleNamespace(
            evaluate_user_quota=lambda user: QuotaDecision(
                allowed=True,
                plan=PlanName.FREE,
                monthly_upload_limit=20,
                monthly_uploads_used=0,
                monthly_success_limit=20,
                monthly_successes_used=0,
                remaining_uploads=20,
                remaining_successes=20,
                max_batch_size=2,
            )
        ),
        processing=processing,
    )
    context = SimpleNamespace(
        bot=bot,
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(max_images_per_batch=10),
                "services": services,
                "inflight_limiter": DenyInflightLimiter(),
            }
        ),
    )
    uploads = [
        TelegramImageUpload(
            file_id="file-1",
            filename="passport-1.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://chat/1/message/2/file/1",
            external_message_id="1",
            external_file_id="file-1",
        )
    ]

    asyncio.run(
        process_upload_batch(
            context=context,
            chat_id=1,
            external_user_id="12345",
            display_name="Agency A",
            uploads=uploads,
        )
    )

    assert processing.calls == 0
    assert len(bot.messages) == 1
    assert "ضغط" in bot.messages[0][1]


def test_inflight_limiter_cancellation_does_not_leak_global_slot():
    async def run() -> None:
        limiter = InflightLimiter(
            max_inflight_upload_batches=1,
            acquire_timeout_seconds=0.1,
        )
        first = await limiter.try_acquire("user-1")
        assert first is not None

        task = asyncio.create_task(limiter.try_acquire("user-2"))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        first.release()
        permit = await limiter.try_acquire("user-2")
        assert permit is not None
        permit.release()

    asyncio.run(run())


def test_inflight_limiter_allows_same_user_up_to_global_limit():
    async def run() -> None:
        limiter = InflightLimiter(
            max_inflight_upload_batches=2,
            acquire_timeout_seconds=0.1,
        )
        first = await limiter.try_acquire("user-1")
        second = await limiter.try_acquire("user-1")

        assert first is not None
        assert second is not None

        first.release()
        second.release()

    asyncio.run(run())


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
