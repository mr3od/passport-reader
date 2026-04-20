"""Per-chat serial processing queue with live status message.

Replaces the old concurrent-batch model to avoid Telegram rate-limit
thrashing when a user sends many images across multiple media groups.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING

from passport_platform.enums import ChannelName
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, TimedOut

if TYPE_CHECKING:
    from passport_platform import TrackedProcessingResult
    from telegram.ext import ContextTypes

    from passport_telegram.bot import TelegramImageUpload

logger = logging.getLogger(__name__)

# ── Item state ────────────────────────────────────────────────────────────────


class ItemState(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(slots=True)
class QueueItem:
    """Single image in the per-chat queue."""

    upload: TelegramImageUpload
    state: ItemState = ItemState.PENDING
    display_name: str | None = None
    failure_reason: str | None = None
    payload: bytes | None = None
    tracked_result: TrackedProcessingResult | None = None
    delivered: bool = False


# ── Per-chat queue ────────────────────────────────────────────────────────────

RESULT_CB_PREFIX = "q:r:"
ERRORS_CB = "q:errors"
EXTRACTION_TIMEOUT_SECONDS = 120.0


@dataclass
class ChatQueue:
    """FIFO queue for a single chat with status-message tracking."""

    chat_id: int
    external_user_id: str
    display_name: str | None = None
    items: list[QueueItem] = field(default_factory=list)
    status_message_id: int | None = None
    _last_edit_ts: float = 0.0
    _worker_task: asyncio.Task | None = field(default=None, repr=False)
    _needs_reposition: bool = False

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def done_count(self) -> int:
        return sum(1 for i in self.items if i.state in (ItemState.SUCCESS, ItemState.FAILED))

    @property
    def success_count(self) -> int:
        return sum(1 for i in self.items if i.state is ItemState.SUCCESS)

    @property
    def fail_count(self) -> int:
        return sum(1 for i in self.items if i.state is ItemState.FAILED)

    @property
    def pending_count(self) -> int:
        return sum(1 for i in self.items if i.state is ItemState.PENDING)

    @property
    def is_complete(self) -> bool:
        return (
            self.total > 0
            and self.pending_count == 0
            and not any(i.state is ItemState.PROCESSING for i in self.items)
        )

    @property
    def all_delivered(self) -> bool:
        return self.is_complete and all(
            i.delivered for i in self.items if i.state is ItemState.SUCCESS
        )

    def success_items(self) -> list[QueueItem]:
        return [i for i in self.items if i.state is ItemState.SUCCESS]

    def failed_items(self) -> list[QueueItem]:
        return [i for i in self.items if i.state is ItemState.FAILED]


# ── Queue manager ─────────────────────────────────────────────────────────────


class ChatQueueManager:
    """Manages per-chat queues and their worker tasks."""

    def __init__(
        self,
        *,
        chat_message_interval: float = 1.0,
        max_concurrent_extractions: int = 4,
        queue_idle_cleanup_seconds: float = 300.0,
    ) -> None:
        self._queues: dict[int, ChatQueue] = {}
        self._chat_interval = chat_message_interval
        self._extraction_sem = asyncio.Semaphore(max_concurrent_extractions)
        self._cleanup_timeout = queue_idle_cleanup_seconds

    def get_queue(self, chat_id: int) -> ChatQueue | None:
        return self._queues.get(chat_id)

    def enqueue(
        self,
        *,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        external_user_id: str,
        display_name: str | None,
        uploads: list[TelegramImageUpload],
    ) -> ChatQueue:
        """Add uploads to the per-chat queue, starting a worker if needed."""
        queue = self._queues.get(chat_id)
        worker_active = (
            queue is not None
            and queue._worker_task is not None
            and not queue._worker_task.done()
        )

        if queue is None or not worker_active:
            # Fresh queue (or old one with finished worker).
            queue = ChatQueue(
                chat_id=chat_id,
                external_user_id=external_user_id,
                display_name=display_name,
            )
            self._queues[chat_id] = queue
        else:
            # Worker is active — flag for repositioning on next edit.
            queue._needs_reposition = True

        for u in uploads:
            queue.items.append(QueueItem(upload=u))

        if queue._worker_task is None or queue._worker_task.done():
            queue._worker_task = asyncio.create_task(
                self._run_worker(queue, context),
                name=f"chat-queue-{chat_id}",
            )

        return queue

    async def shutdown(self) -> None:
        """Cancel all active workers."""
        tasks = [
            q._worker_task
            for q in self._queues.values()
            if q._worker_task and not q._worker_task.done()
        ]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._queues.clear()

    # ── worker loop ───────────────────────────────────────────────────────

    async def _run_worker(
        self,
        queue: ChatQueue,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Drain the queue serially, updating the status message."""
        from passport_platform import (
            ExternalProvider,
            ProcessingFailedError,
            ProcessUploadCommand,
            QuotaExceededError,
            UserBlockedError,
            UserStatus,
        )
        from passport_platform.schemas.commands import EnsureUserCommand

        from passport_telegram.bot import _download_upload
        from passport_telegram.messages import quota_exceeded_text, user_blocked_text

        services = context.application.bot_data["services"]

        try:
            user = await asyncio.to_thread(
                services.users.get_or_create_user,
                EnsureUserCommand(
                    external_provider=ExternalProvider.TELEGRAM,
                    external_user_id=queue.external_user_id,
                    display_name=queue.display_name,
                ),
            )
            if user.status is UserStatus.BLOCKED:
                await _safe_send(context, queue.chat_id, user_blocked_text())
                return

            await self._send_or_edit_status(context, queue)

            while True:
                item = _next_pending(queue)
                if item is None:
                    break

                item.state = ItemState.PROCESSING
                await self._send_or_edit_status(context, queue)

                async with self._extraction_sem:
                    try:
                        payload = await _download_upload(context, item.upload)
                        item.payload = payload
                        tracked = await asyncio.wait_for(
                            asyncio.to_thread(
                                services.processing.process_bytes,
                                ProcessUploadCommand(
                                    external_provider=ExternalProvider.TELEGRAM,
                                    external_user_id=queue.external_user_id,
                                    display_name=queue.display_name,
                                    channel=ChannelName.TELEGRAM,
                                    filename=item.upload.filename,
                                    mime_type=item.upload.mime_type,
                                    source_ref=item.upload.source_ref,
                                    payload=payload,
                                    external_message_id=item.upload.external_message_id,
                                    external_file_id=item.upload.external_file_id,
                                ),
                            ),
                            timeout=EXTRACTION_TIMEOUT_SECONDS,
                        )
                    except QuotaExceededError as exc:
                        item.state = ItemState.FAILED
                        item.failure_reason = "تجاوز الحد المسموح"
                        for remaining in queue.items:
                            if remaining.state is ItemState.PENDING:
                                remaining.state = ItemState.FAILED
                                remaining.failure_reason = "تجاوز الحد المسموح"
                        await self._send_or_edit_status(context, queue, force=True)
                        await _safe_send(context, queue.chat_id, quota_exceeded_text(exc.decision))
                        return
                    except UserBlockedError:
                        await _safe_send(context, queue.chat_id, user_blocked_text())
                        return
                    except TimeoutError:
                        logger.warning("queue_extraction_timeout chat_id=%s", queue.chat_id)
                        item.state = ItemState.FAILED
                        item.failure_reason = "انتهت مهلة المعالجة"
                        await self._send_or_edit_status(context, queue)
                        continue
                    except (ProcessingFailedError, Exception):
                        logger.exception("queue_processing_failed")
                        item.state = ItemState.FAILED
                        item.failure_reason = "خطأ في المعالجة"
                        await self._send_or_edit_status(context, queue)
                        continue

                    if not tracked.is_complete:
                        item.state = ItemState.FAILED
                        item.failure_reason = (
                            "الصورة ليست لجواز واضح"
                            if not tracked.is_passport
                            else "لم تكتمل المعالجة"
                        )
                    else:
                        item.state = ItemState.SUCCESS
                        item.tracked_result = tracked
                        data = tracked.extracted_data
                        if data and data.full_name_ar:
                            item.display_name = data.full_name_ar
                        elif data and data.full_name_en:
                            item.display_name = data.full_name_en
                        else:
                            item.display_name = tracked.filename

                    await self._send_or_edit_status(context, queue)

            # Final update.
            logger.info(
                "queue_complete chat_id=%s total=%s ok=%s fail=%s",
                queue.chat_id,
                queue.total,
                queue.success_count,
                queue.fail_count,
            )
            await self._send_or_edit_status(context, queue, force=True)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("chat_queue_worker_crashed chat_id=%s", queue.chat_id)
        finally:
            logger.info("queue_worker_exit chat_id=%s", queue.chat_id)
            self._schedule_cleanup(queue.chat_id)

    # ── status message ────────────────────────────────────────────────────

    async def _send_or_edit_status(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        queue: ChatQueue,
        *,
        force: bool = False,
    ) -> None:
        """Create or edit the live status message, respecting rate limits."""
        now = time.monotonic()
        elapsed = now - queue._last_edit_ts
        if not force and elapsed < self._chat_interval:
            await asyncio.sleep(self._chat_interval - elapsed)

        # Reposition: delete old message, send fresh one at bottom.
        # Safe because only the worker calls this method.
        if queue._needs_reposition and queue.status_message_id is not None:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(
                    chat_id=queue.chat_id, message_id=queue.status_message_id
                )
            queue.status_message_id = None
            queue._needs_reposition = False

        text = _build_status_text(queue)
        keyboard = _build_status_keyboard(queue)
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        try:
            if queue.status_message_id is None:
                msg = await context.bot.send_message(
                    chat_id=queue.chat_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                queue.status_message_id = msg.message_id
            else:
                await context.bot.edit_message_text(
                    chat_id=queue.chat_id,
                    message_id=queue.status_message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
        except RetryAfter as exc:
            await asyncio.sleep(_retry_seconds(exc.retry_after))
            await self._send_or_edit_status(context, queue, force=True)
            return
        except BadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                logger.warning("status_edit_failed: %s", exc)
        except TimedOut:
            logger.warning("status_edit_timed_out chat_id=%s", queue.chat_id)

        queue._last_edit_ts = time.monotonic()

    # ── cleanup ───────────────────────────────────────────────────────────

    def _schedule_cleanup(self, chat_id: int) -> None:
        """Remove queue after timeout, but only if all results are delivered."""
        loop = asyncio.get_running_loop()
        loop.call_later(self._cleanup_timeout, self._try_cleanup, chat_id)

    def _try_cleanup(self, chat_id: int) -> None:
        queue = self._queues.get(chat_id)
        if queue is None:
            return
        # Don't clean up if worker is still running.
        if queue._worker_task and not queue._worker_task.done():
            return
        # Don't clean up if there are undelivered results — user may
        # still click buttons. Reschedule.
        if not queue.all_delivered and queue.success_count > 0:
            loop = asyncio.get_running_loop()
            loop.call_later(self._cleanup_timeout, self._try_cleanup, chat_id)
            return
        self._queues.pop(chat_id, None)


# ── Status text builders ──────────────────────────────────────────────────────


def _build_status_text(queue: ChatQueue) -> str:
    """Build the live status message content."""
    if queue.is_complete:
        return _build_complete_text(queue)

    total = queue.total
    done = queue.done_count

    lines: list[str] = [f"📋 معالجة {total} جواز\n"]

    if total <= 20:
        for idx, item in enumerate(queue.items, 1):
            lines.append(_item_line(idx, item))
    else:
        for idx, item in enumerate(queue.items, 1):
            if item.state in (ItemState.SUCCESS, ItemState.FAILED, ItemState.PROCESSING):
                lines.append(_item_line(idx, item))
            else:
                break
        remaining = (
            total - done - (1 if any(i.state is ItemState.PROCESSING for i in queue.items) else 0)
        )
        if remaining > 0:
            lines.append(f"⬚ {remaining} في الانتظار")

    lines.append("")
    remaining = total - done
    lines.append(
        f"✅ ناجح: {queue.success_count}  ❌ فشل: {queue.fail_count}  ⏳ متبقي: {remaining}"
    )
    return "\n".join(lines)


def _build_complete_text(queue: ChatQueue) -> str:
    """Final summary when all items are processed."""
    lines = [f"✅ اكتملت معالجة {queue.total} جواز\n"]
    lines.append(f"ناجح: {queue.success_count}  ❌ فشل: {queue.fail_count}")

    if queue.fail_count > 0:
        lines.append("\nالأخطاء:")
        for idx, item in enumerate(queue.items, 1):
            if item.state is ItemState.FAILED:
                lines.append(f"  {idx}. {item.failure_reason or 'خطأ غير محدد'}")

    return "\n".join(lines)


def _item_line(idx: int, item: QueueItem) -> str:
    if item.state is ItemState.SUCCESS:
        label = item.display_name or f"جواز {idx}"
        tick = "☑" if item.delivered else "✅"
        return f"{tick} {idx}. {label}"
    if item.state is ItemState.FAILED:
        return f"❌ {idx}. {item.failure_reason or 'خطأ'}"
    if item.state is ItemState.PROCESSING:
        return f"⏳ {idx}. جاري المعالجة..."
    return f"⬚ {idx}."


def _build_status_keyboard(queue: ChatQueue) -> list[list[InlineKeyboardButton]]:
    """Build inline keyboard with per-result buttons and error button."""
    rows: list[list[InlineKeyboardButton]] = []

    # Individual result buttons for undelivered successes.
    for idx, item in enumerate(queue.items):
        if item.state is ItemState.SUCCESS and not item.delivered:
            name = item.display_name or f"جواز {idx + 1}"
            rows.append(
                [
                    InlineKeyboardButton(
                        f"📄 {name}",
                        callback_data=f"{RESULT_CB_PREFIX}{idx}",
                    )
                ]
            )

    if queue.fail_count > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    f"❌ تفاصيل الأخطاء ({queue.fail_count})",
                    callback_data=ERRORS_CB,
                )
            ]
        )

    return rows


# ── Callback handlers ─────────────────────────────────────────────────────────


async def handle_single_result_callback(
    context: ContextTypes.DEFAULT_TYPE,
    queue_manager: ChatQueueManager,
    chat_id: int,
    callback_query_id: str,
    item_index: int,
) -> None:
    """Send a single result by index."""
    queue = queue_manager.get_queue(chat_id)
    if queue is None or item_index >= len(queue.items):
        await context.bot.answer_callback_query(callback_query_id, text="النتيجة غير متوفرة")
        return

    item = queue.items[item_index]
    if item.state is not ItemState.SUCCESS:
        await context.bot.answer_callback_query(callback_query_id, text="النتيجة غير متوفرة")
        return

    await context.bot.answer_callback_query(callback_query_id)

    from passport_telegram.messages import format_success_text

    idx = item_index + 1
    if item.tracked_result is not None:
        caption = format_success_text(item.tracked_result, position=idx, total=queue.total)
    else:
        name = item.display_name or f"جواز {idx}"
        caption = f"✅ الصورة {idx} من {queue.total}\n{name}"

    try:
        if item.payload:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=item.payload,
                caption=caption,
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown")
        item.delivered = True
    except RetryAfter as exc:
        await asyncio.sleep(_retry_seconds(exc.retry_after))
        try:
            if item.payload:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=item.payload,
                    caption=caption,
                    parse_mode="Markdown",
                )
            else:
                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown")
            item.delivered = True
        except Exception:
            logger.warning("result_delivery_retry_failed chat_id=%s", chat_id)
    except Exception:
        logger.warning("result_delivery_failed chat_id=%s idx=%s", chat_id, item_index)

    # Refresh keyboard only if worker is done (no race).
    # If worker is still running, it will pick up the change on its next cycle.
    worker_done = queue._worker_task is None or queue._worker_task.done()
    if worker_done:
        await queue_manager._send_or_edit_status(context, queue, force=True)


async def handle_errors_callback(
    context: ContextTypes.DEFAULT_TYPE,
    queue_manager: ChatQueueManager,
    chat_id: int,
    callback_query_id: str,
) -> None:
    """Send consolidated error report."""
    queue = queue_manager.get_queue(chat_id)
    if queue is None:
        await context.bot.answer_callback_query(callback_query_id, text="لا توجد أخطاء")
        return

    failures = queue.failed_items()
    if not failures:
        await context.bot.answer_callback_query(callback_query_id, text="لا توجد أخطاء")
        return

    await context.bot.answer_callback_query(callback_query_id)

    lines = [f"❌ تقرير الأخطاء ({len(failures)} من {queue.total})\n"]
    for item in failures:
        idx = queue.items.index(item) + 1
        lines.append(f"{idx}. {item.failure_reason or 'خطأ غير محدد'}")

    lines.append("\nأعد إرسال الصور التي فشلت بصورة أوضح أو كملف.")
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _retry_seconds(retry_after: int | float | timedelta) -> float:
    """Convert RetryAfter.retry_after to seconds."""
    if isinstance(retry_after, timedelta):
        return retry_after.total_seconds()
    return float(retry_after)


def _next_pending(queue: ChatQueue) -> QueueItem | None:
    for item in queue.items:
        if item.state is ItemState.PENDING:
            return item
    return None


async def _safe_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
) -> None:
    """Send a message, absorbing Telegram errors."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.warning("safe_send_failed chat_id=%s", chat_id)
