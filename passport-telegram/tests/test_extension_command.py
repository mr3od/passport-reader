from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from passport_platform.enums import UserStatus
from passport_telegram.bot import build_application, extension_command
from passport_telegram.extension import ExtensionFetchError
from passport_telegram.messages import (
    extension_fetch_error_text,
    extension_installing_text,
    user_blocked_text,
)
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes


class FakeReplyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.photos: list[dict] = []
        self.documents: list[dict] = []

    async def reply_text(self, text: str, parse_mode: str | None = None) -> None:
        self.replies.append(text)

    async def reply_photo(self, *, photo, caption: str) -> None:
        self.photos.append({"photo": photo, "caption": caption})

    async def reply_document(self, *, document, filename: str) -> None:
        self.documents.append({"document": document, "filename": filename})


def _make_update(reply: FakeReplyMessage) -> Update:
    return cast(
        Update,
        SimpleNamespace(
            effective_chat=SimpleNamespace(id=1),
            effective_user=SimpleNamespace(
                id=12345, first_name="Agency", last_name="A", username=None
            ),
            effective_message=reply,
            message=reply,
        ),
    )


def _make_context(*, services: object, settings: object) -> ContextTypes.DEFAULT_TYPE:
    return cast(
        ContextTypes.DEFAULT_TYPE,
        SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    "services": services,
                    "settings": settings,
                }
            ),
        ),
    )


def _active_user():
    return SimpleNamespace(id=1, external_user_id="12345", status=UserStatus.ACTIVE)


def _blocked_user():
    return SimpleNamespace(id=1, external_user_id="12345", status=UserStatus.BLOCKED)


def _make_services(user):
    return SimpleNamespace(users=SimpleNamespace(get_or_create_user=lambda command: user))


def _make_settings(*, has_token: bool = True, has_repo: bool = True):
    token = SimpleNamespace(get_secret_value=lambda: "gh-token") if has_token else None
    return SimpleNamespace(
        github_release_read_token=token,
        github_repo="owner/repo" if has_repo else None,
    )


def test_extension_command_blocked_user_gets_blocked_reply():
    reply = FakeReplyMessage()
    services = _make_services(_blocked_user())
    settings = _make_settings()
    context = _make_context(services=services, settings=settings)
    update = _make_update(reply)

    asyncio.run(extension_command(update, context))

    assert len(reply.replies) == 1
    assert reply.replies[0] == user_blocked_text()
    assert len(reply.photos) == 0
    assert len(reply.documents) == 0


def test_extension_command_missing_config_sends_error():
    reply = FakeReplyMessage()
    services = _make_services(_active_user())
    settings = _make_settings(has_token=False)
    context = _make_context(services=services, settings=settings)
    update = _make_update(reply)

    asyncio.run(extension_command(update, context))

    assert len(reply.replies) == 1
    assert reply.replies[0] == extension_fetch_error_text()
    assert len(reply.photos) == 0
    assert len(reply.documents) == 0


def test_extension_command_fetch_error_sends_arabic_error():
    reply = FakeReplyMessage()
    services = _make_services(_active_user())
    settings = _make_settings()
    context = _make_context(services=services, settings=settings)
    update = _make_update(reply)

    with patch(
        "passport_telegram.bot.fetch_extension_zip",
        new=AsyncMock(side_effect=ExtensionFetchError("network error")),
    ):
        asyncio.run(extension_command(update, context))

    # First reply is the installing message, second is the error
    assert len(reply.replies) == 2
    assert reply.replies[0] == extension_installing_text()
    assert reply.replies[1] == extension_fetch_error_text()
    assert len(reply.photos) == 0
    assert len(reply.documents) == 0


def test_extension_command_success_sends_steps_and_zip():
    reply = FakeReplyMessage()
    services = _make_services(_active_user())
    settings = _make_settings()
    context = _make_context(services=services, settings=settings)
    update = _make_update(reply)

    fake_zip = b"PK\x03\x04fake-zip-bytes"

    fake_step = MagicMock()
    fake_step.__enter__ = MagicMock(return_value=b"png-bytes")
    fake_step.__exit__ = MagicMock(return_value=False)

    with (
        patch(
            "passport_telegram.bot.fetch_extension_zip",
            new=AsyncMock(return_value=fake_zip),
        ),
        patch("pathlib.Path.open", return_value=fake_step),
    ):
        asyncio.run(extension_command(update, context))

    assert len(reply.replies) == 1
    assert reply.replies[0] == extension_installing_text()
    assert len(reply.photos) == 3
    assert len(reply.documents) == 1
    assert reply.documents[0]["filename"] == "passport-masar-extension.zip"


def test_extension_command_is_registered():
    settings_mock = MagicMock()
    settings_mock.bot_token.get_secret_value.return_value = "fake-token"
    settings_mock.max_concurrent_extractions = 4
    settings_mock.chat_message_interval_seconds = 1.0
    settings_mock.queue_idle_cleanup_seconds = 300.0

    with patch("passport_telegram.bot._build_bot_services", return_value=MagicMock()):
        app = build_application(settings_mock)

    handler_commands = set()
    for group_handlers in app.handlers.values():
        for handler in group_handlers:
            if isinstance(handler, CommandHandler):
                handler_commands.update(handler.commands)

    assert "extension" in handler_commands
