"""Persistent Reply Keyboard used as NovaBot's primary navigation."""

from __future__ import annotations

from telegram import ReplyKeyboardMarkup


FILE_TOOLS_BUTTON = "📁 File Tools"
SECURITY_TOOLS_BUTTON = "🔐 Security Tools"
SETTINGS_BUTTON = "⚙️ Settings"
DONATE_STARS_BUTTON = "⭐ Donate Stars"
HELP_BUTTON = "ℹ️ Help"

MAIN_MENU_BUTTONS = (
    FILE_TOOLS_BUTTON,
    SECURITY_TOOLS_BUTTON,
    SETTINGS_BUTTON,
    DONATE_STARS_BUTTON,
    HELP_BUTTON,
)


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Return the persistent two-column main menu."""

    return ReplyKeyboardMarkup(
        keyboard=[
            [FILE_TOOLS_BUTTON, SECURITY_TOOLS_BUTTON],
            [SETTINGS_BUTTON, DONATE_STARS_BUTTON],
            [HELP_BUTTON],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )