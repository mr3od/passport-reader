from __future__ import annotations

import asyncio
import logging
import mimetypes
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from passport_core import PassportWorkflow
from passport_core.config import Settings as CoreSettings
from passport_platform import (
    ChannelName,
    Database,
    ExternalProvider,
    PlatformSettings,
    ProcessingFailedError,
    ProcessingService,
    ProcessUploadCommand,
    QuotaExceededError,
    QuotaService,
    UploadService,
    UserBlockedError,
    UserService,
)
from passport_platform.repositories import UploadsRepository, UsageRepository, UsersRepository
from telegram import Document, InputMediaPhoto, Message, PhotoSize, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from passport_telegram.config import TelegramSettings
from passport_telegram.messages import (
    batch_started_text,
    format_failure_text,
    format_success_text,
    help_text,
    processing_error_text,
    quota_exceeded_text,
    unauthorized_text,
    unsupported_file_text,
    user_blocked_text,
    welcome_text,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


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
    processing: ProcessingService

    def close(self) -> None:
        self.processing.close()


def build_application(settings: TelegramSettings) -> Application:
    services = BotServices(processing=_build_processing_service(settings))
    collector = MediaGroupCollector()

    application = Application.builder().token(settings.bot_token.get_secret_value()).build()
    application.bot_data["settings"] = settings
    application.bot_data["services"] = services
    application.bot_data["collector"] = collector
    application.bot_data["media_group_jobs"] = {}

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.ALL, image_message_handler)
    )
    return application


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed_chat(context, update.effective_chat.id if update.effective_chat else None):
        await _reply_text(update, unauthorized_text())
        return
    await _reply_text(update, welcome_text())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed_chat(context, update.effective_chat.id if update.effective_chat else None):
        await _reply_text(update, unauthorized_text())
        return
    await _reply_text(update, help_text())


async def image_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    if not _is_allowed_chat(context, chat.id):
        await _reply_text(update, unauthorized_text())
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

        jobs[key] = context.job_queue.run_once(
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
    key = context.job.data["key"]
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

    batch = uploads[: settings.max_images_per_batch]
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
            result = tracked.workflow_result
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

        if not result.is_complete:
            await context.bot.send_message(
                chat_id=chat_id,
                text=format_failure_text(result, position=index, total=len(batch)),
            )
            continue

        await context.bot.send_media_group(
            chat_id=chat_id,
            media=_build_success_media_group(
                result=result,
                caption=format_success_text(result, position=index, total=len(batch)),
            ),
        )


async def telegram_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logging.getLogger(__name__).exception("telegram_update_failed", exc_info=context.error)


def _build_processing_service(settings: TelegramSettings) -> ProcessingService:
    core_settings = _build_core_settings(settings)
    workflow = PassportWorkflow(settings=core_settings)
    platform_settings = _build_platform_settings(settings)
    db = Database(platform_settings.db_path)
    db.initialize()
    return ProcessingService(
        users=UserService(UsersRepository(db)),
        quotas=QuotaService(UsageRepository(db)),
        uploads=UploadService(UploadsRepository(db), UsageRepository(db)),
        workflow=workflow,
    )


def _build_core_settings(settings: TelegramSettings) -> CoreSettings:
    core_settings = CoreSettings(_env_file=settings.core_env_file)
    root = settings.core_root_dir

    core_settings.assets_dir = _resolve_path(root, core_settings.assets_dir)
    core_settings.template_path = _resolve_path(root, core_settings.template_path)
    core_settings.face_model_path = _resolve_path(root, core_settings.face_model_path)
    core_settings.local_storage_dir = _resolve_path(root, core_settings.local_storage_dir)
    core_settings.data_store_path = _resolve_path(root, core_settings.data_store_path)
    return core_settings


def _build_platform_settings(settings: TelegramSettings) -> PlatformSettings:
    platform_settings = PlatformSettings(_env_file=settings.platform_env_file)
    platform_settings.db_path = _resolve_path(settings.platform_root_dir, platform_settings.db_path)
    return platform_settings


def _resolve_path(root: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return (root / value).resolve()


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


def _is_allowed_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int | None) -> bool:
    if chat_id is None:
        return False
    settings: TelegramSettings = context.application.bot_data["settings"]
    allowed = settings.allowed_chat_id_set
    return not allowed or chat_id in allowed


async def _reply_text(update: Update, text: str) -> None:
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(text)


def _build_success_media_group(*, result, caption: str) -> list[InputMediaPhoto]:
    passport_image = BytesIO(result.image_bytes)
    passport_image.name = result.filename

    face_crop = BytesIO(result.face_crop_bytes or b"")
    face_crop.name = f"{Path(result.filename).stem}_face.jpg"

    return [
        InputMediaPhoto(
            media=passport_image,
            caption=caption,
        ),
        InputMediaPhoto(
            media=face_crop,
        ),
    ]
