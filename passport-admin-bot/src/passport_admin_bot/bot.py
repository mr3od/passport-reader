from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from passport_platform import (
    BroadcastService,
    ExternalProvider,
    PlanName,
    ReportingService,
    UserService,
    UserStatus,
    build_platform_runtime,
)
from telegram import BotCommand, Message, PhotoSize, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from passport_admin_bot.config import AdminBotSettings
from passport_admin_bot.menus import main_menu_markup, render_users, route_callback
from passport_admin_bot.messages import (
    admin_only_text,
    broadcast_download_failed_text,
    broadcast_help_text,
    broadcast_queued_text,
    format_monthly_usage_report,
    format_recent_uploads,
    format_user_usage_report,
    help_text,
    setplan_help_text,
    user_not_found_text,
    user_plan_updated_text,
    user_status_updated_text,
    welcome_text,
)


@dataclass(slots=True)
class BotServices:
    users: UserService
    reporting: ReportingService
    broadcasts: BroadcastService

    def close(self) -> None:
        return None


COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("admin", "Interactive admin panel"),
    BotCommand("stats", "Monthly usage summary"),
    BotCommand("recent", "Recent uploads"),
    BotCommand("usage", "Usage for one agency"),
    BotCommand("setplan", "Change agency plan"),
    BotCommand("block", "Block agency access"),
    BotCommand("unblock", "Restore agency access"),
    BotCommand("broadcast", "Queue a broadcast"),
]


def build_application(settings: AdminBotSettings) -> Application:
    """Build the admin bot application with command and callback handlers."""
    services = _build_bot_services()
    application = Application.builder().token(settings.bot_token.get_secret_value()).build()
    application.bot_data["settings"] = settings
    application.bot_data["services"] = services

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("recent", recent_command))
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(CommandHandler("setplan", setplan_command))
    application.add_handler(CommandHandler("block", block_command))
    application.add_handler(CommandHandler("unblock", unblock_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CallbackQueryHandler(_callback_handler))

    application.post_init = _post_init
    return application


async def _post_init(application: Application) -> None:
    """Register bot commands with Telegram on startup."""
    await application.bot.set_my_commands(COMMANDS)


# ── Commands ─────────────────────────────────────────────────────────


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_admin(update, context):
        return
    await _reply_text(update, welcome_text())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_admin(update, context):
        return
    await _reply_text(update, help_text())


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the interactive admin panel as a new message."""
    if not await _require_admin(update, context):
        return
    text, markup = main_menu_markup()
    msg = update.effective_message
    if msg:
        await msg.reply_text(text, reply_markup=markup)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_admin(update, context):
        return
    services: BotServices = context.application.bot_data["services"]
    report = await asyncio.to_thread(services.reporting.get_monthly_usage_report)
    await _reply_text(update, format_monthly_usage_report(report))


async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_admin(update, context):
        return
    limit = 10
    if context.args:
        limit = _safe_positive_int(context.args[0], default=10, maximum=20)
    services: BotServices = context.application.bot_data["services"]
    records = await asyncio.to_thread(services.reporting.list_recent_uploads, limit=limit)
    await _reply_text(update, format_recent_uploads(records))


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show usage for a user. If no ID given, show interactive user picker."""
    if not await _require_admin(update, context):
        return
    args = context.args or []
    if len(args) != 1:
        text, markup = await render_users(context, 0)
        msg = update.effective_message
        if msg:
            await msg.reply_text(
                "Select a user to view usage:",
                reply_markup=markup,
            )
        return

    services: BotServices = context.application.bot_data["services"]
    user = services.users.get_by_external_identity(ExternalProvider.TELEGRAM, args[0])
    if user is None:
        await _reply_text(update, user_not_found_text(args[0]))
        return

    report = await asyncio.to_thread(services.reporting.get_user_usage_report, user.id)
    await _reply_text(update, format_user_usage_report(report))


async def setplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Change user plan. If args missing, show interactive user picker."""
    if not await _require_admin(update, context):
        return
    args = context.args or []
    if len(args) < 1:
        text, markup = await render_users(context, 0)
        msg = update.effective_message
        if msg:
            await msg.reply_text(
                "Select a user to change plan:",
                reply_markup=markup,
            )
        return

    if len(args) != 2:
        await _reply_text(update, setplan_help_text())
        return

    services: BotServices = context.application.bot_data["services"]
    user = services.users.get_by_external_identity(ExternalProvider.TELEGRAM, args[0])
    if user is None:
        await _reply_text(update, user_not_found_text(args[0]))
        return

    plan = _parse_plan(args[1])
    if plan is None:
        await _reply_text(update, setplan_help_text())
        return

    updated = services.users.change_plan(user.id, plan)
    await _reply_text(update, user_plan_updated_text(updated))


async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_user_status(update, context, UserStatus.BLOCKED, "block")


async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_user_status(update, context, UserStatus.ACTIVE, "unblock")


async def broadcast_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
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

    message = getattr(update, "message", None)
    reply_to_message = message.reply_to_message if message else None
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


# ── Callback handler ─────────────────────────────────────────────────


async def _callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Route inline keyboard callbacks, with admin check."""
    if not _is_admin_user(context, update):
        query = update.callback_query
        if query:
            await query.answer(admin_only_text(), show_alert=True)
        return
    await route_callback(update, context)


# ── Internals ────────────────────────────────────────────────────────


async def telegram_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logging.getLogger(__name__).exception(
        "admin_bot_update_failed",
        exc_info=context.error,
    )


def _build_bot_services() -> BotServices:
    platform_runtime = build_platform_runtime()
    return BotServices(
        users=platform_runtime.users,
        reporting=platform_runtime.reporting,
        broadcasts=platform_runtime.broadcasts,
    )


def _is_admin_user(context: ContextTypes.DEFAULT_TYPE, update: Update) -> bool:
    settings: AdminBotSettings = context.application.bot_data["settings"]
    user = update.effective_user
    if user is None:
        return False
    if user.id in settings.admin_user_id_set:
        return True
    username = user.username
    if not username:
        return False
    return username.lower() in settings.admin_username_set


async def _require_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if _is_admin_user(context, update):
        return True
    await _reply_text(update, admin_only_text())
    return False


async def _set_user_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    status: UserStatus,
    command_name: str,
) -> None:
    """Change user status. If no ID given, show interactive user picker."""
    if not await _require_admin(update, context):
        return
    args = context.args or []
    if len(args) != 1:
        text, markup = await render_users(context, 0)
        msg = update.effective_message
        if msg:
            await msg.reply_text(
                f"Select a user to {command_name}:",
                reply_markup=markup,
            )
        return

    services: BotServices = context.application.bot_data["services"]
    user = services.users.get_by_external_identity(ExternalProvider.TELEGRAM, args[0])
    if user is None:
        await _reply_text(update, user_not_found_text(args[0]))
        return

    updated = services.users.change_status(user.id, status)
    await _reply_text(update, user_status_updated_text(updated))


def _safe_positive_int(value: str, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return default
    if parsed < 1:
        return default
    return min(parsed, maximum)


def _parse_plan(value: str) -> PlanName | None:
    try:
        return PlanName(value.lower())
    except ValueError:
        return None


def _largest_photo(message: Message | None) -> PhotoSize | None:
    if message is None or not message.photo:
        return None
    return message.photo[-1]


async def _reply_text(update: Update, text: str) -> None:
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(text)
