from __future__ import annotations

import asyncio
from types import SimpleNamespace

from passport_platform import PlanName, QuotaDecision
from passport_platform.enums import UserStatus

from passport_telegram.bot import TelegramImageUpload, process_upload_batch


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class FakeProcessingService:
    def __init__(self) -> None:
        self.calls = 0

    def process_bytes(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("process_bytes should not be called when batch exceeds the limit")


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
