"""Telegram command handlers exposed from the bot menu."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from keyboards.inline_buttons import main_menu_keyboard


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain the commands available from the Telegram menu."""

    del context
    message = update.effective_message
    if message is not None:
        await message.reply_text(
            "CyberBot help\n\n"
            "/start — open CyberBot\n"
            "/donate — support CyberBot with Telegram Stars\n"
            "/help — show this help\n"
            "/settings — open settings"
        )


async def settings_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Open the current settings screen."""

    del context
    message = update.effective_message
    if message is not None:
        await message.reply_text(
            "⚙️ Settings\n\nSettings are ready for the next CyberBot update.",
            reply_markup=main_menu_keyboard(),
        )