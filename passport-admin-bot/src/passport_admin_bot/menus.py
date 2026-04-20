"""Inline keyboard navigation for the admin bot.

All interactive menus edit a single message in-place. Callback data uses
a compact ``action:param1:param2`` format to stay within Telegram's 64-byte
callback_data limit.

Actions
-------
menu            – main menu
stats           – monthly stats
recent:P        – recent uploads, page P
users:P         – user list, page P
user:ID         – single user detail
usage:ID        – user usage report
setplan:ID      – plan picker for user
doplan:ID:PLAN  – execute plan change
block:ID        – confirm block
unblock:ID      – confirm unblock
doblk:ID:S      – execute status change (S = blocked|active)
bcast           – broadcast prompt
"""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING

from passport_platform import PlanName, UserStatus
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from passport_admin_bot.messages import (
    format_monthly_usage_report,
    format_recent_uploads,
    format_user_usage_report,
)

if TYPE_CHECKING:
    from passport_admin_bot.bot import BotServices

PAGE_SIZE = 8


def _services(context: ContextTypes.DEFAULT_TYPE) -> BotServices:
    return context.application.bot_data["services"]


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _back_row(data: str = "menu") -> list[InlineKeyboardButton]:
    return [_btn("« Back", data)]


# ── Main menu ────────────────────────────────────────────────────────


async def main_menu_markup(
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[str, InlineKeyboardMarkup]:
    """Return dashboard text and keyboard for the main admin menu."""
    services = _services(context)
    report = await asyncio.to_thread(services.reporting.get_monthly_usage_report)
    users = await asyncio.to_thread(services.users.list_users, limit=200)
    active = sum(1 for u in users if u.status == UserStatus.ACTIVE)
    blocked = sum(1 for u in users if u.status == UserStatus.BLOCKED)

    text = (
        "⚙️ Admin Panel\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Users: {len(users)} ({active} active, {blocked} blocked)\n"
        f"📤 Uploads this month: {report.total_uploads}\n"
        f"✅ Successful: {report.total_successes}\n"
        f"❌ Failed: {report.total_failures}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [_btn("📊 Stats", "stats"), _btn("🕐 Recent", "recent:0")],
        [_btn("👥 Users", "users:0"), _btn("📢 Broadcast", "bcast")],
    ]
    return text, InlineKeyboardMarkup(kb)


# ── Stats ────────────────────────────────────────────────────────────


async def render_stats(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    """Fetch and format monthly stats."""
    services = _services(context)
    report = await asyncio.to_thread(services.reporting.get_monthly_usage_report)
    text = format_monthly_usage_report(report)
    kb = [_back_row()]
    return text, InlineKeyboardMarkup(kb)


# ── Recent uploads ───────────────────────────────────────────────────


async def render_recent(
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Fetch recent uploads with pagination."""
    services = _services(context)
    limit = PAGE_SIZE
    offset = page * PAGE_SIZE
    # Fetch one extra to know if there's a next page.
    records = await asyncio.to_thread(
        services.reporting.list_recent_uploads,
        limit=limit + 1,
        offset=offset,
    )
    has_next = len(records) > limit
    records = records[:limit]

    text = format_recent_uploads(records) if records else "No recent uploads."
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(_btn("« Prev", f"recent:{page - 1}"))
    if has_next:
        nav.append(_btn("Next »", f"recent:{page + 1}"))
    kb = [nav] if nav else []
    kb.append(_back_row())
    return text, InlineKeyboardMarkup(kb)


# ── User list ────────────────────────────────────────────────────────


async def render_users(
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Paginated user list with selection buttons."""
    services = _services(context)
    users = await asyncio.to_thread(services.users.list_users, limit=200)
    total_pages = max(1, math.ceil(len(users) / PAGE_SIZE))
    page = min(page, total_pages - 1)
    page_users = users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    text = f"👥 Users ({len(users)} total) — page {page + 1}/{total_pages}"
    kb: list[list[InlineKeyboardButton]] = []
    for u in page_users:
        status_icon = "🚫" if u.status == UserStatus.BLOCKED else ""
        label = f"{status_icon}{u.display_name or u.external_user_id} [{u.plan.value}]"
        kb.append([_btn(label, f"user:{u.id}")])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(_btn("« Prev", f"users:{page - 1}"))
    if page < total_pages - 1:
        nav.append(_btn("Next »", f"users:{page + 1}"))
    if nav:
        kb.append(nav)
    kb.append(_back_row())
    return text, InlineKeyboardMarkup(kb)


# ── Single user detail ───────────────────────────────────────────────


async def render_user(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Show user detail with action buttons."""
    services = _services(context)
    user = await asyncio.to_thread(services.users.get_by_id, user_id)
    if user is None:
        return "User not found.", InlineKeyboardMarkup([_back_row("users:0")])

    report = await asyncio.to_thread(services.reporting.get_user_usage_report, user.id)
    text = format_user_usage_report(report)

    kb: list[list[InlineKeyboardButton]] = [
        [_btn("📊 Usage", f"usage:{user_id}"), _btn("📋 Set Plan", f"setplan:{user_id}")],
    ]
    if user.status == UserStatus.BLOCKED:
        kb.append([_btn("✅ Unblock", f"doblk:{user_id}:active")])
    else:
        kb.append([_btn("🚫 Block", f"doblk:{user_id}:blocked")])
    kb.append(_back_row("users:0"))
    return text, InlineKeyboardMarkup(kb)


# ── Usage report ─────────────────────────────────────────────────────


async def render_usage(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Detailed usage report for a user."""
    services = _services(context)
    report = await asyncio.to_thread(services.reporting.get_user_usage_report, user_id)
    text = format_user_usage_report(report)
    kb = [_back_row(f"user:{user_id}")]
    return text, InlineKeyboardMarkup(kb)


# ── Plan picker ──────────────────────────────────────────────────────


async def render_plan_picker(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Show plan selection buttons."""
    services = _services(context)
    user = await asyncio.to_thread(services.users.get_by_id, user_id)
    if user is None:
        return "User not found.", InlineKeyboardMarkup([_back_row("users:0")])

    name = user.display_name or user.external_user_id
    text = f"Select plan for {name}\nCurrent: {user.plan.value}"
    kb = [
        [
            _btn(
                f"{'● ' if user.plan == p else ''}{p.value}",
                f"doplan:{user_id}:{p.value}",
            )
            for p in PlanName
        ],
        _back_row(f"user:{user_id}"),
    ]
    return text, InlineKeyboardMarkup(kb)


# ── Execute plan change ──────────────────────────────────────────────


async def execute_plan_change(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    plan_value: str,
) -> tuple[str, InlineKeyboardMarkup]:
    """Change user plan and return confirmation."""
    services = _services(context)
    plan = PlanName(plan_value)
    updated = await asyncio.to_thread(services.users.change_plan, user_id, plan)
    name = updated.display_name or updated.external_user_id
    text = f"✅ {name} → {updated.plan.value}"
    kb = [_back_row(f"user:{user_id}")]
    return text, InlineKeyboardMarkup(kb)


# ── Execute block/unblock ────────────────────────────────────────────


async def execute_status_change(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    status_value: str,
) -> tuple[str, InlineKeyboardMarkup]:
    """Change user status and return confirmation."""
    services = _services(context)
    status = UserStatus(status_value)
    updated = await asyncio.to_thread(services.users.change_status, user_id, status)
    name = updated.display_name or updated.external_user_id
    icon = "🚫" if status == UserStatus.BLOCKED else "✅"
    text = f"{icon} {name} → {updated.status.value}"
    kb = [_back_row(f"user:{user_id}")]
    return text, InlineKeyboardMarkup(kb)


# ── Broadcast ────────────────────────────────────────────────────────


def render_broadcast() -> tuple[str, InlineKeyboardMarkup]:
    """Show broadcast instructions."""
    text = (
        "📢 Broadcast\n\n"
        "Send one of:\n"
        "• /broadcast <message> — text broadcast\n"
        "• Reply to a photo with /broadcast — photo broadcast"
    )
    kb = [_back_row()]
    return text, InlineKeyboardMarkup(kb)


# ── Router ───────────────────────────────────────────────────────────


async def route_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Route callback query to the appropriate renderer and edit the message."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    data = query.data or "menu"
    parts = data.split(":")
    action = parts[0]

    text: str
    markup: InlineKeyboardMarkup

    if action == "menu":
        text, markup = await main_menu_markup(context)
    elif action == "stats":
        text, markup = await render_stats(context)
    elif action == "recent":
        page = int(parts[1]) if len(parts) > 1 else 0
        text, markup = await render_recent(context, page)
    elif action == "users":
        page = int(parts[1]) if len(parts) > 1 else 0
        text, markup = await render_users(context, page)
    elif action == "user":
        text, markup = await render_user(context, int(parts[1]))
    elif action == "usage":
        text, markup = await render_usage(context, int(parts[1]))
    elif action == "setplan":
        text, markup = await render_plan_picker(context, int(parts[1]))
    elif action == "doplan":
        text, markup = await execute_plan_change(context, int(parts[1]), parts[2])
    elif action == "doblk":
        text, markup = await execute_status_change(context, int(parts[1]), parts[2])
    elif action == "bcast":
        text, markup = render_broadcast()
    else:
        text, markup = await main_menu_markup(context)

    await query.edit_message_text(text=text, reply_markup=markup)
