"""Handlers for the bot welcome screen."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from database.database import Database
from keyboards.inline_buttons import welcome_keyboard


WELCOME_TEXT = (
    "🤖 CyberBot\n\n"
    "Your Smart Digital Assistant\n\n"
    "Welcome to CyberBot. Choose an option below to get started."
)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register the user for future features and show the welcome screen."""

    user = update.effective_user
    message = update.effective_message
    database = context.application.bot_data["database"]

    if user is not None:
        database.ensure_user(user.id, user.username)

    if message is not None:
        await message.reply_text(WELCOME_TEXT, reply_markup=welcome_keyboard())