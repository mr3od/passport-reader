from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from passport_platform import (
    AuthService,
    BroadcastContentType,
    BroadcastService,
    ExternalProvider,
    ProcessingService,
    QuotaService,
    RecordsService,
    ReportingService,
    UserService,
    UserStatus,
    build_platform_runtime,
    build_processing_runtime,
)
from passport_platform.models.user import User
from passport_platform.schemas.commands import EnsureUserCommand
from telegram import CallbackQuery, Document, Message, PhotoSize, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from passport_telegram.config import TelegramSettings
from passport_telegram.extension import ExtensionFetchError, fetch_extension_zip
from passport_telegram.messages import (
    extension_fetch_error_text,
    extension_installing_text,
    extension_step1_caption,
    extension_step2_caption,
    extension_step3_caption,
    format_masar_status_text,
    format_user_usage_report,
    help_text,
    temp_token_text,
    unsupported_file_text,
    user_blocked_text,
    welcome_text,
)
from passport_telegram.queue import (
    ERRORS_CB,
    RESULT_CB_PREFIX,
    RETRY_CB,
    ChatQueueManager,
    handle_errors_callback,
    handle_retry_callback,
    handle_single_result_callback,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}

_EXTENSION_ASSETS_DIR = Path(__file__).parent / "assets" / "extension"
_EXTENSION_STEPS = [
    (_EXTENSION_ASSETS_DIR / "step1.png", extension_step1_caption),
    (_EXTENSION_ASSETS_DIR / "step2.png", extension_step2_caption),
    (_EXTENSION_ASSETS_DIR / "step3.png", extension_step3_caption),
]


@dataclass(slots=True)
class TelegramImageUpload:
    file_id: str
    filename: str
    mime_type: str
    source_ref: str
    external_message_id: str
    external_file_id: str


@dataclass(slots=True)
class PendingMediaGroup:
    chat_id: int
    message_id: int
    external_user_id: str
    display_name: str | None
    uploads: list[TelegramImageUpload] = field(default_factory=list)


class MediaGroupCollector:
    def __init__(self) -> None:
        self._batches: dict[str, PendingMediaGroup] = {}

    def add(
        self,
        key: str,
        *,
        chat_id: int,
        message_id: int,
        external_user_id: str,
        display_name: str | None,
        upload: TelegramImageUpload,
    ) -> None:
        batch = self._batches.setdefault(
            key,
            PendingMediaGroup(
                chat_id=chat_id,
                message_id=message_id,
                external_user_id=external_user_id,
                display_name=display_name,
            ),
        )
        batch.uploads.append(upload)

    def pop(self, key: str) -> PendingMediaGroup | None:
        return self._batches.pop(key, None)


@dataclass(slots=True)
class BotServices:
    auth: AuthService
    processing: ProcessingService
    users: UserService
    quotas: QuotaService
    reporting: ReportingService
    records: RecordsService
    broadcasts: BroadcastService

    def close(self) -> None:
        self.processing.close()


def build_application(settings: TelegramSettings) -> Application:
    services = _build_bot_services(settings)
    collector = MediaGroupCollector()
    queue_manager = ChatQueueManager(
        chat_message_interval=settings.chat_message_interval_seconds,
        max_concurrent_extractions=settings.max_concurrent_extractions,
        queue_idle_cleanup_seconds=settings.queue_idle_cleanup_seconds,
    )

    application = (
        Application.builder()
        .token(settings.bot_token.get_secret_value())
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["services"] = services
    application.bot_data["collector"] = collector
    application.bot_data["media_group_jobs"] = {}
    application.bot_data["queue_manager"] = queue_manager

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("me", me_command))
    application.add_handler(CommandHandler("token", token_command))
    application.add_handler(CommandHandler("masar", masar_command))
    application.add_handler(CommandHandler("extension", extension_command))
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.ALL, image_message_handler)
    )
    return application


# ── Command handlers ──────────────────────────────────────────────────────────


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_text(update, welcome_text())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_text(update, help_text())


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services: BotServices = context.application.bot_data["services"]
    user = await _get_or_create_user(update, services)
    report = await asyncio.to_thread(services.reporting.get_user_usage_report, user.id)
    await _reply_text(update, format_user_usage_report(report))


async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services: BotServices = context.application.bot_data["services"]
    user = await _get_or_create_user(update, services)
    if user.status is UserStatus.BLOCKED:
        await _reply_text(update, user_blocked_text())
        return
    issued = await asyncio.to_thread(services.auth.issue_temp_token, user.id)
    await _reply_text(update, temp_token_text(issued), parse_mode="Markdown")


async def masar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services: BotServices = context.application.bot_data["services"]
    user = await _get_or_create_user(update, services)
    if user.status is UserStatus.BLOCKED:
        await _reply_text(update, user_blocked_text())
        return
    records = await asyncio.to_thread(services.records.get_masar_pending, user.id)
    await _reply_text(update, format_masar_status_text(records))


async def extension_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services: BotServices = context.application.bot_data["services"]
    user = await _get_or_create_user(update, services)
    if user.status is UserStatus.BLOCKED:
        await _reply_text(update, user_blocked_text())
        return

    cfg: TelegramSettings = context.application.bot_data["settings"]
    if not cfg.github_release_read_token or not cfg.github_repo:
        await _reply_text(update, extension_fetch_error_text())
        return

    await _reply_text(update, extension_installing_text())

    try:
        zip_bytes = await fetch_extension_zip(
            token=cfg.github_release_read_token.get_secret_value(),
            repo=cfg.github_repo,
        )
    except ExtensionFetchError:
        await _reply_text(update, extension_fetch_error_text())
        return

    if update.effective_message is None:
        return

    for step_path, caption_fn in _EXTENSION_STEPS:
        with step_path.open("rb") as f:
            await update.effective_message.reply_photo(photo=f, caption=caption_fn())

    await update.effective_message.reply_document(
        document=io.BytesIO(zip_bytes),
        filename="passport-masar-extension.zip",
    )


# ── Image handling ────────────────────────────────────────────────────────────


async def image_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    upload = _extract_upload(message)
    if upload is None:
        await _reply_text(update, unsupported_file_text())
        return

    settings: TelegramSettings = context.application.bot_data["settings"]

    if message.media_group_id:
        key = f"{chat.id}:{message.media_group_id}"
        collector: MediaGroupCollector = context.application.bot_data["collector"]
        collector.add(
            key,
            chat_id=chat.id,
            message_id=message.message_id,
            external_user_id=_external_user_id(update),
            display_name=_display_name(update),
            upload=upload,
        )

        jobs: dict[str, object] = context.application.bot_data["media_group_jobs"]
        existing_job = jobs.get(key)
        if existing_job is not None:
            existing_job.schedule_removal()

        job_queue = context.job_queue
        if job_queue is None:
            raise RuntimeError("telegram job queue is not configured")

        jobs[key] = job_queue.run_once(
            flush_media_group,
            when=settings.album_collection_window_seconds,
            data={"key": key},
            name=key,
        )
        return

    # Single image — enqueue directly.
    queue_manager: ChatQueueManager = context.application.bot_data["queue_manager"]
    queue_manager.enqueue(
        context=context,
        chat_id=chat.id,
        external_user_id=_external_user_id(update),
        display_name=_display_name(update),
        uploads=[upload],
    )


async def flush_media_group(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None or not isinstance(job.data, dict):
        return
    key = cast(Any, job.data).get("key")
    if not isinstance(key, str):
        return
    collector: MediaGroupCollector = context.application.bot_data["collector"]
    jobs: dict[str, object] = context.application.bot_data["media_group_jobs"]
    pending = collector.pop(key)
    jobs.pop(key, None)
    if pending is None:
        return

    queue_manager: ChatQueueManager = context.application.bot_data["queue_manager"]
    queue_manager.enqueue(
        context=context,
        chat_id=pending.chat_id,
        external_user_id=pending.external_user_id,
        display_name=pending.display_name,
        uploads=pending.uploads,
    )


# ── Callback query handler ───────────────────────────────────────────────────


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if query is None:
        return

    chat = update.effective_chat
    if chat is None:
        return

    queue_manager: ChatQueueManager = context.application.bot_data["queue_manager"]
    data = query.data or ""

    if data == ERRORS_CB:
        await handle_errors_callback(context, queue_manager, chat.id, query.id)
    elif data == RETRY_CB:
        await handle_retry_callback(context, queue_manager, chat.id, query.id)
    elif data.startswith(RESULT_CB_PREFIX):
        try:
            item_index = int(data[len(RESULT_CB_PREFIX) :])
        except ValueError:
            await query.answer()
            return
        await handle_single_result_callback(context, queue_manager, chat.id, query.id, item_index)
    else:
        await query.answer()


# ── Broadcast ─────────────────────────────────────────────────────────────────


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
    application.bot_data["broadcast_worker_task"] = asyncio.create_task(
        broadcast_worker(application)
    )


async def _post_shutdown(application: Application) -> None:
    # Shutdown queue manager.
    queue_manager: ChatQueueManager | None = application.bot_data.get("queue_manager")
    if queue_manager is not None:
        await queue_manager.shutdown()

    task = application.bot_data.get("broadcast_worker_task")
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# ── Internal helpers ──────────────────────────────────────────────────────────


def _build_bot_services(settings: TelegramSettings) -> BotServices:
    platform_runtime = build_platform_runtime()
    processing_runtime = build_processing_runtime(platform_runtime=platform_runtime)
    processing = processing_runtime.processing
    if processing is None:
        raise RuntimeError("passport-core runtime is not configured for passport-telegram")

    return BotServices(
        auth=platform_runtime.auth,
        processing=processing,
        users=platform_runtime.users,
        quotas=platform_runtime.quotas,
        reporting=platform_runtime.reporting,
        records=platform_runtime.records,
        broadcasts=platform_runtime.broadcasts,
    )


async def _get_or_create_user(update: Update, services: BotServices) -> User:
    return await asyncio.to_thread(
        services.users.get_or_create_user,
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id=_external_user_id(update),
            display_name=_display_name(update),
        ),
    )


async def _download_upload(
    context: ContextTypes.DEFAULT_TYPE,
    upload: TelegramImageUpload,
) -> bytes:
    telegram_file = await context.bot.get_file(upload.file_id)
    payload = await telegram_file.download_as_bytearray()
    return bytes(payload)


def _extract_upload(message: Message) -> TelegramImageUpload | None:
    if message.photo:
        photo: PhotoSize = message.photo[-1]
        return TelegramImageUpload(
            file_id=photo.file_id,
            filename=f"telegram_photo_{message.message_id}.jpg",
            mime_type="image/jpeg",
            source_ref=_source_ref(message, photo.file_id),
            external_message_id=str(message.message_id),
            external_file_id=photo.file_id,
        )

    document = message.document
    if document is None or not _is_supported_document(document):
        return None

    filename = document.file_name or f"telegram_document_{message.message_id}.jpg"
    mime_type = document.mime_type or mimetypes.guess_type(filename)[0] or "image/jpeg"
    return TelegramImageUpload(
        file_id=document.file_id,
        filename=filename,
        mime_type=mime_type,
        source_ref=_source_ref(message, document.file_id),
        external_message_id=str(message.message_id),
        external_file_id=document.file_id,
    )


def _is_supported_document(document: Document) -> bool:
    if document.mime_type and document.mime_type.startswith("image/"):
        return True
    if not document.file_name:
        return False
    return Path(document.file_name).suffix.lower() in IMAGE_EXTENSIONS


def _source_ref(message: Message, file_id: str) -> str:
    chat_id = message.chat.id if message.chat else "unknown"
    return f"telegram://chat/{chat_id}/message/{message.message_id}/file/{file_id}"


def _external_user_id(update: Update) -> str:
    user = update.effective_user
    return str(user.id) if user is not None else "unknown"


def _display_name(update: Update) -> str | None:
    user = update.effective_user
    if user is None:
        return None
    parts = [user.first_name, user.last_name]
    full_name = " ".join(part.strip() for part in parts if part and part.strip())
    if full_name:
        return full_name
    return user.username


async def _reply_text(update: Update, text: str, parse_mode: str | None = None) -> None:
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(text, parse_mode=parse_mode)


async def telegram_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logging.getLogger(__name__).exception("telegram_update_failed", exc_info=context.error)
