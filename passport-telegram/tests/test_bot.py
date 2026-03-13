from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from passport_platform import IssuedTempToken, PlanName, QuotaDecision
from passport_platform.enums import UserStatus

from passport_telegram.bot import (
    TelegramImageUpload,
    account_command,
    plan_command,
    process_upload_batch,
    token_command,
    usage_command,
)


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class FakeReplyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeProcessingService:
    def __init__(self) -> None:
        self.calls = 0

    def process_bytes(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("process_bytes should not be called when batch exceeds the limit")


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
                record=None,  # type: ignore[arg-type]
            )
        ),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_chat_id_set=set()),
                "services": services,
            }
        )
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1),
        effective_user=SimpleNamespace(id=12345, first_name="Agency", last_name="A", username=None),
        effective_message=reply,
    )

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
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_chat_id_set=set()),
                "services": services,
            }
        )
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1),
        effective_user=SimpleNamespace(id=12345, first_name="Agency", last_name="A", username=None),
        effective_message=reply,
    )

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
    context = SimpleNamespace(
        args=[],
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_chat_id_set=set()),
                "services": services,
            }
        ),
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1),
        effective_user=SimpleNamespace(id=12345, first_name="Agency", last_name="A", username=None),
        effective_message=reply,
    )

    asyncio.run(usage_command(update, context))

    assert len(reply.replies) == 1
    assert "Agency A" in reply.replies[0]
    assert "18" in reply.replies[0]


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
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(allowed_chat_id_set=set()),
                "services": services,
            }
        ),
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1),
        effective_user=SimpleNamespace(id=12345, first_name="Agency", last_name="A", username=None),
        effective_message=reply,
    )

    asyncio.run(plan_command(update, context))

    assert len(reply.replies) == 1
    assert "Agency A" in reply.replies[0]
    assert "pro" in reply.replies[0]
    assert "active" in reply.replies[0]


def test_process_upload_batch_rejects_batches_above_plan_limit():
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
    assert "3" in bot.messages[0][1]
    assert "2" in bot.messages[0][1]
