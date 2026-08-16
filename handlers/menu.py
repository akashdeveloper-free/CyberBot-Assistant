"""Reply-keyboard routing and inline submenu navigation."""

from __future__ import annotations

import logging

from telegram import CallbackQuery, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from handlers.commands import help_handler, settings_handler
from handlers.donation import DONATION_MENU_TEXT
from handlers.donation import donate_command_handler
from keyboards.inline_buttons import back_to_main_keyboard, donation_menu_keyboard
from keyboards.reply_keyboard import (
    DONATE_STARS_BUTTON,
    FILE_TOOLS_BUTTON,
    HELP_BUTTON,
    SECURITY_TOOLS_BUTTON,
    SETTINGS_BUTTON,
    VIDEO_DOWNLOADER_BUTTON,
)

logger = logging.getLogger(__name__)

MAIN_MENU_TEXT = (
    "🤖 NovaBot — Main Menu\n"
    "Your Smart Digital Assistant"
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
        context.user_data.pop("WAITING_FOR_CUSTOM_STARS", None)
        context.user_data.pop("PENDING_DONATION_AMOUNT", None)
        await edit_callback_screen(query, MAIN_MENU_TEXT, None)
        return

    if query.data == "menu:welcome":
        context.user_data.pop("WAITING_FOR_CUSTOM_STARS", None)
        context.user_data.pop("PENDING_DONATION_AMOUNT", None)
        await edit_callback_screen(query, MAIN_MENU_TEXT, None)
        return

    if query.data == "menu:donate":
        context.user_data.pop("WAITING_FOR_CUSTOM_STARS", None)
        context.user_data.pop("PENDING_DONATION_AMOUNT", None)
        await edit_callback_screen(
            query,
            DONATION_MENU_TEXT,
            donation_menu_keyboard(),
        )
        return

    if query.data.startswith("future:"):
        await edit_callback_screen(
            query,
            "This feature is planned for a future NovaBot update.\n\n"
            "Please choose an available option from the menu.",
            back_to_main_keyboard(),
        )


async def reply_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Route one of the six persistent main-menu buttons."""

    message = update.effective_message
    if message is None or not message.text:
        return

    if message.text == DONATE_STARS_BUTTON:
        await donate_command_handler(update, context)
        return
    if message.text == HELP_BUTTON:
        await help_handler(update, context)
        return
    if message.text == SETTINGS_BUTTON:
        await settings_handler(update, context)
        return

    feature_names = {
        VIDEO_DOWNLOADER_BUTTON: "🎬 Video Downloader",
        FILE_TOOLS_BUTTON: "📁 File Tools",
        SECURITY_TOOLS_BUTTON: "🔐 Security Tools",
    }
    feature_name = feature_names.get(message.text)
    if feature_name is None:
        return

    await message.reply_text(
        f"{feature_name}\n\n"
        "This feature is planned for a future NovaBot update.\n\n"
        "Please choose another option from the menu.",
        reply_markup=back_to_main_keyboard(),
    )