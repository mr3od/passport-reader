from __future__ import annotations

from passport_platform import MonthlyUsageReport, PlanName, RecentUploadRecord, UserUsageReport
from passport_platform.models.user import User


def welcome_text() -> str:
    return "Passport Reader admin bot.\n\nUse /admin to view available operator commands."


def help_text() -> str:
    return (
        "Admin commands:\n"
        "/admin - show admin commands\n"
        "/stats - monthly usage summary\n"
        "/recent [count] - recent uploads\n"
        "/usage <telegram_user_id> - usage for one agency\n"
        "/setplan <telegram_user_id> <free|basic|pro> - change plan\n"
        "/block <telegram_user_id> - block agency access\n"
        "/unblock <telegram_user_id> - restore agency access\n"
        "/broadcast <message> - queue a text broadcast\n"
        "/broadcast - reply to a photo to queue a photo broadcast"
    )


def admin_only_text() -> str:
    return "This command is available to admin users only."


def usage_help_text() -> str:
    return "Usage: /usage <telegram_user_id>"


def setplan_help_text() -> str:
    return "Usage: /setplan <telegram_user_id> <free|basic|pro>"


def status_help_text(command_name: str) -> str:
    return f"Usage: /{command_name} <telegram_user_id>"


def broadcast_help_text() -> str:
    return "Usage:\n/broadcast <message>\nor reply to a photo with /broadcast"


def broadcast_queued_text() -> str:
    return "Broadcast queued successfully."


def broadcast_download_failed_text() -> str:
    return "Could not download the photo for broadcast."


def user_not_found_text(external_user_id: str) -> str:
    return f"User not found: {external_user_id}"


def format_monthly_usage_report(report: MonthlyUsageReport) -> str:
    return (
        "Monthly usage summary:\n"
        f"Total users: {report.total_users}\n"
        f"Active users: {report.active_users}\n"
        f"Blocked users: {report.blocked_users}\n"
        f"Total uploads: {report.total_uploads}\n"
        f"Successful processes: {report.total_successes}\n"
        f"Failed processes: {report.total_failures}"
    )


def format_recent_uploads(records: list[RecentUploadRecord]) -> str:
    if not records:
        return "No recent uploads."

    lines = ["Recent uploads:"]
    for record in records:
        lines.append(
            f"- {record.external_user_id} | {record.filename} | "
            f"{record.upload_status.value} | {record.passport_number or record.error_code or '-'}"
        )
    return "\n".join(lines)


def format_user_usage_report(report: UserUsageReport) -> str:
    user = report.user
    return (
        f"User: {user.display_name or user.external_user_id}\n"
        f"Telegram user id: {user.external_user_id}\n"
        f"Plan: {user.plan.value}\n"
        f"Status: {user.status.value}\n"
        f"Uploads this month: {report.upload_count}\n"
        f"Successful processes: {report.success_count}\n"
        f"Failed processes: {report.failure_count}\n"
        f"Remaining uploads: {report.quota_decision.remaining_uploads}\n"
        f"Remaining successful processes: {report.quota_decision.remaining_successes}"
    )


def user_plan_updated_text(user: User) -> str:
    return f"Updated {user.external_user_id} to plan {user.plan.value}."


def user_status_updated_text(user: User) -> str:
    return f"Updated {user.external_user_id} to status {user.status.value}."


def parse_plan(value: str) -> PlanName | None:
    try:
        return PlanName(value.lower())
    except ValueError:
        return None
