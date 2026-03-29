from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from passport_platform import (
    AuthService,
    ChannelName,
    ExternalProvider,
    ProcessingFailedError,
    ProcessingService,
    ProcessUploadCommand,
    QuotaExceededError,
    QuotaService,
    RecordsService,
    ReportingService,
    UserBlockedError,
    UserService,
    UserStatus,
    build_platform_runtime,
    build_processing_runtime,
)
from passport_platform.models.user import User
from passport_platform.schemas.commands import EnsureUserCommand
from telegram import Document, Message, PhotoSize, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from passport_telegram.config import TelegramSettings
from passport_telegram.extension import ExtensionFetchError, fetch_extension_zip
from passport_telegram.messages import (
    batch_limit_exceeded_text,
    batch_started_text,
    extension_fetch_error_text,
    extension_installing_text,
    extension_step1_caption,
    extension_step2_caption,
    extension_step3_caption,
    format_failure_text,
    format_masar_status_text,
    format_success_text,
    format_user_plan_text,
    format_user_usage_report,
    help_text,
    processing_error_text,
    quota_exceeded_text,
    temp_token_text,
    unsupported_file_text,
    usage_help_text,
    user_blocked_text,
    welcome_text,
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

    def close(self) -> None:
        self.processing.close()


def build_application(settings: TelegramSettings) -> Application:
    services = _build_bot_services(settings)
    collector = MediaGroupCollector()

    application = Application.builder().token(settings.bot_token.get_secret_value()).build()
    application.bot_data["settings"] = settings
    application.bot_data["services"] = services
    application.bot_data["collector"] = collector
    application.bot_data["media_group_jobs"] = {}

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("account", account_command))
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(CommandHandler("plan", plan_command))
    application.add_handler(CommandHandler("token", token_command))
    application.add_handler(CommandHandler("masar", masar_command))
    application.add_handler(CommandHandler("extension", extension_command))
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.ALL, image_message_handler)
    )
    return application


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_text(update, welcome_text())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_text(update, help_text())


async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services: BotServices = context.application.bot_data["services"]
    user = await _get_or_create_user(update, services)
    report = await asyncio.to_thread(services.reporting.get_user_usage_report, user.id)
    await _reply_text(update, format_user_usage_report(report))


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services: BotServices = context.application.bot_data["services"]
    user = await _get_or_create_user(update, services)
    await _reply_text(update, format_user_plan_text(user))


async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services: BotServices = context.application.bot_data["services"]
    user = await _get_or_create_user(update, services)
    if user.status is UserStatus.BLOCKED:
        await _reply_text(update, user_blocked_text())
        return
    issued = await asyncio.to_thread(services.auth.issue_temp_token, user.id)
    await _reply_text(update, temp_token_text(issued))


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

    for step_path, caption_fn in _EXTENSION_STEPS:
        with step_path.open("rb") as f:
            await update.message.reply_photo(photo=f, caption=caption_fn())

    await update.message.reply_document(
        document=io.BytesIO(zip_bytes),
        filename="passport-masar-extension.zip",
    )


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services: BotServices = context.application.bot_data["services"]
    if context.args:
        await _reply_text(update, usage_help_text())
        return
    user = await _get_or_create_user(update, services)
    report = await asyncio.to_thread(services.reporting.get_user_usage_report, user.id)
    await _reply_text(update, format_user_usage_report(report))


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

    await process_upload_batch(
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

    await process_upload_batch(
        context=context,
        chat_id=pending.chat_id,
        external_user_id=pending.external_user_id,
        display_name=pending.display_name,
        uploads=pending.uploads,
    )


async def process_upload_batch(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    external_user_id: str,
    display_name: str | None,
    uploads: list[TelegramImageUpload],
) -> None:
    settings: TelegramSettings = context.application.bot_data["settings"]
    services: BotServices = context.application.bot_data["services"]
    user = await asyncio.to_thread(
        services.users.get_or_create_user,
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id=external_user_id,
            display_name=display_name,
        ),
    )
    if user.status is UserStatus.BLOCKED:
        await context.bot.send_message(chat_id=chat_id, text=user_blocked_text())
        return

    quota_decision = await asyncio.to_thread(services.quotas.evaluate_user_quota, user)
    max_batch_size = min(settings.max_images_per_batch, quota_decision.max_batch_size)
    if len(uploads) > max_batch_size:
        await context.bot.send_message(
            chat_id=chat_id,
            text=batch_limit_exceeded_text(total=len(uploads), limit=max_batch_size),
        )
        return

    batch = uploads
    if len(batch) > 1:
        await context.bot.send_message(chat_id=chat_id, text=batch_started_text(len(batch)))

    for index, upload in enumerate(batch, start=1):
        try:
            payload = await _download_upload(context, upload)
            tracked = await asyncio.to_thread(
                services.processing.process_bytes,
                ProcessUploadCommand(
                    external_provider=ExternalProvider.TELEGRAM,
                    external_user_id=external_user_id,
                    display_name=display_name,
                    channel=ChannelName.TELEGRAM,
                    filename=upload.filename,
                    mime_type=upload.mime_type,
                    source_ref=upload.source_ref,
                    payload=payload,
                    external_message_id=upload.external_message_id,
                    external_file_id=upload.external_file_id,
                ),
            )
        except QuotaExceededError as exc:
            await context.bot.send_message(chat_id=chat_id, text=quota_exceeded_text(exc.decision))
            break
        except UserBlockedError:
            await context.bot.send_message(chat_id=chat_id, text=user_blocked_text())
            break
        except ProcessingFailedError:
            logging.getLogger(__name__).exception("telegram_processing_failed")
            await context.bot.send_message(chat_id=chat_id, text=processing_error_text())
            continue
        except Exception:
            logging.getLogger(__name__).exception("telegram_processing_failed")
            await context.bot.send_message(chat_id=chat_id, text=processing_error_text())
            continue

        if not tracked.is_complete:
            await context.bot.send_message(
                chat_id=chat_id,
                text=format_failure_text(tracked, position=index, total=len(batch)),
            )
            continue

        await context.bot.send_photo(
            chat_id=chat_id,
            photo=payload,
            caption=format_success_text(tracked, position=index, total=len(batch)),
            parse_mode="Markdown",
        )


async def telegram_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logging.getLogger(__name__).exception("telegram_update_failed", exc_info=context.error)


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


async def _reply_text(update: Update, text: str) -> None:
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(text)
