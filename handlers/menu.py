"""Main menu and future-feature navigation handlers."""

from __future__ import annotations

import logging

from telegram import CallbackQuery, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from handlers.start import WELCOME_TEXT
from keyboards.inline_buttons import (
    back_to_main_keyboard,
    donation_menu_keyboard,
    main_menu_keyboard,
    welcome_keyboard,
)

logger = logging.getLogger(__name__)

MAIN_MENU_TEXT = (
    "🤖 CyberBot — Main Menu\n\n"
    "Your Smart Digital Assistant\n\n"
    "Select an available option:"
)

DONATION_MENU_TEXT = (
    "⭐ Donate Stars\n\n"
    "Support CyberBot with Telegram Stars.\n"
    "Choose a donation amount:"
)


async def edit_callback_screen(
    query: CallbackQuery,
    text: str,
    reply_markup: object,
) -> None:
    """Edit an existing callback message while tolerating duplicate taps."""

    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning("Could not edit callback message: %s", exc)


async def menu_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle welcome, main menu, and inactive future-feature buttons."""

    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    if query.data == "menu:main":
        context.user_data.pop("awaiting_custom_stars", None)
        await edit_callback_screen(query, MAIN_MENU_TEXT, main_menu_keyboard())
        return

    if query.data == "menu:welcome":
        context.user_data.pop("awaiting_custom_stars", None)
        await edit_callback_screen(query, WELCOME_TEXT, welcome_keyboard())
        return

    if query.data == "menu:donate":
        context.user_data.pop("awaiting_custom_stars", None)
        await edit_callback_screen(
            query,
            DONATION_MENU_TEXT,
            donation_menu_keyboard(),
        )
        return

    if query.data.startswith("future:"):
        await edit_callback_screen(
            query,
            "This feature is planned for a future CyberBot update.\n\n"
            "Please choose an available option from the menu.",
            back_to_main_keyboard(),
        )