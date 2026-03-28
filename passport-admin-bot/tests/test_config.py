from __future__ import annotations

from passport_admin_bot.config import AdminBotSettings
from pydantic import SecretStr


def test_admin_bot_settings_parse_admin_identity_lists():
    settings = AdminBotSettings.model_construct(
        bot_token=SecretStr("token"),
        admin_user_ids="552002791, 743379791 ",
        admin_usernames="@mr3od, admin2 ",
    )

    assert settings.admin_user_id_set == {552002791, 743379791}
    assert settings.admin_username_set == {"mr3od", "admin2"}


def test_admin_bot_settings_keep_log_level_default():
    settings = AdminBotSettings.model_construct(bot_token=SecretStr("token"))

    assert settings.log_level == "INFO"
