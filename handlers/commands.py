"""Telegram command handlers exposed from the bot menu."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from keyboards.reply_keyboard import main_reply_keyboard


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain the commands available from the Telegram menu."""

    del context
    message = update.effective_message
    if message is not None:
        await message.reply_text(
            "ℹ️ NovaBot Help\n\n"
            "/start — open NovaBot\n"
            "/donate — support NovaBot with Telegram Stars\n"
            "/help — show this help\n"
            "/settings — open settings\n\n"
            "You can also use the persistent keyboard below to navigate.",
            reply_markup=main_reply_keyboard(),
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
            "⚙️ Settings\n\nSettings are ready for the next NovaBot update.",
            reply_markup=main_reply_keyboard(),
        )