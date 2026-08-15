"""Telegram Stars donation flow handlers."""

from __future__ import annotations

import logging

from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes

from database.database import Database
from keyboards.inline_buttons import (
    back_to_donation_keyboard,
    donation_confirmation_keyboard,
    donation_menu_keyboard,
)
from services.telegram_stars import (
    DONATION_PAYLOAD_PREFIX,
    build_donation_payload,
    create_invoice,
    validate_pre_checkout,
)

logger = logging.getLogger(__name__)

WAITING_FOR_CUSTOM_STARS = "WAITING_FOR_CUSTOM_STARS"
PENDING_DONATION_AMOUNT = "PENDING_DONATION_AMOUNT"
MIN_STARS = 1
MAX_STARS = 2_147_483_647

CUSTOM_AMOUNT_PROMPT = (
    "✏️ Enter Custom Stars Amount\n\n"
    "Please type the number of Stars you want to donate.\n\n"
    "Example:\n"
    "20\n"
    "50\n"
    "100"
)


def _database(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["database"]


async def donation_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle donation amount selection and donation navigation."""

    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()
    action = query.data.split(":", maxsplit=1)[1]

    if action == "custom":
        context.user_data.pop(PENDING_DONATION_AMOUNT, None)
        context.user_data[WAITING_FOR_CUSTOM_STARS] = True
        await query.edit_message_text(
            CUSTOM_AMOUNT_PROMPT,
            reply_markup=back_to_donation_keyboard(),
        )
        return

    if action == "back":
        context.user_data.pop(WAITING_FOR_CUSTOM_STARS, None)
        context.user_data.pop(PENDING_DONATION_AMOUNT, None)
        await query.edit_message_text(
            "⭐ Donate Stars\n\n"
            "Support CyberBot with Telegram Stars.\n"
            "Choose a donation amount:",
            reply_markup=donation_menu_keyboard(),
        )
        return

    if action == "continue":
        amount = context.user_data.get(PENDING_DONATION_AMOUNT)
        if not isinstance(amount, int):
            await query.edit_message_text(
                "No donation amount is waiting for confirmation.\n\n"
                "Please choose an amount again.",
                reply_markup=donation_menu_keyboard(),
            )
            return

        await _send_invoice_from_callback(query, context, amount)
        return

    try:
        amount = int(action)
    except ValueError:
        logger.warning("Unexpected donation callback data: %s", query.data)
        return

    if amount < MIN_STARS or amount > MAX_STARS:
        await query.edit_message_text(
            "Please choose a valid Stars amount.",
            reply_markup=donation_menu_keyboard(),
        )
        return

    context.user_data.pop(WAITING_FOR_CUSTOM_STARS, None)
    context.user_data[PENDING_DONATION_AMOUNT] = amount
    await query.edit_message_text(
        "⭐ CyberBot Donation\n\n"
        "You selected:\n"
        f"{amount} Telegram Stars",
        reply_markup=donation_confirmation_keyboard(),
    )


async def _send_invoice_from_callback(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    amount: int,
) -> None:
    """Create a Telegram Stars invoice after a fixed/custom amount choice."""

    if amount < MIN_STARS or amount > MAX_STARS:
        await query.edit_message_text(
            "Please choose a valid Stars amount.",
            reply_markup=donation_menu_keyboard(),
        )
        return

    if query.message is None:
        logger.warning("Donation callback did not contain a message.")
        return

    chat = query.message.chat
    payload = build_donation_payload(chat.id, amount)

    await query.edit_message_text(
        f"⭐ {amount} Stars donation\n\n"
        "Your secure Telegram payment request is below.",
        reply_markup=back_to_donation_keyboard(),
    )

    await create_invoice(
        bot=context.bot,
        chat_id=chat.id,
        stars=amount,
        payload=payload,
    )
    context.user_data.pop(PENDING_DONATION_AMOUNT, None)


async def custom_amount_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Validate custom Stars input and send an invoice for valid input."""

    if not context.user_data.get(WAITING_FOR_CUSTOM_STARS):
        return

    message = update.effective_message
    if message is None or not message.text:
        return

    raw_amount = message.text.strip()
    try:
        amount = int(raw_amount)
    except ValueError:
        await message.reply_text(
            "Please send a whole number of Stars, for example: 25.",
            reply_markup=back_to_donation_keyboard(),
        )
        return

    if amount < MIN_STARS:
        await message.reply_text(
            "The donation amount must be at least 1 Star.",
            reply_markup=back_to_donation_keyboard(),
        )
        return

    if amount > MAX_STARS:
        await message.reply_text(
            "That amount is too large for a Telegram Stars invoice. "
            "Please choose a smaller amount.",
            reply_markup=back_to_donation_keyboard(),
        )
        return

    user = update.effective_user
    if user is not None:
        _database(context).ensure_user(user.id, user.username)

    payload = build_donation_payload(message.chat_id, amount)
    await message.reply_text(
        f"⭐ {amount} Stars donation\n\n"
        "Your secure Telegram payment request is below.",
        reply_markup=back_to_donation_keyboard(),
    )
    await create_invoice(
        bot=context.bot,
        chat_id=message.chat_id,
        stars=amount,
        payload=payload,
    )
    context.user_data.pop(WAITING_FOR_CUSTOM_STARS, None)


async def pre_checkout_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Approve only valid CyberBot Telegram Stars pre-checkout requests."""

    del context
    query = update.pre_checkout_query
    if query is None:
        return

    is_valid, error_message = validate_pre_checkout(
        currency=query.currency,
        total_amount=query.total_amount,
        invoice_payload=query.invoice_payload,
    )
    await query.answer(ok=is_valid, error_message=error_message)


async def successful_payment_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Persist a successful payment and thank the donor."""

    message = update.effective_message
    payment = message.successful_payment if message else None
    user = update.effective_user
    if payment is None or user is None or message is None:
        logger.warning("Successful payment update was missing expected data.")
        return

    if not payment.invoice_payload.startswith(DONATION_PAYLOAD_PREFIX):
        logger.warning("Ignoring unknown successful payment payload.")
        return

    inserted = _database(context).record_donation(
        user_id=user.id,
        username=user.username,
        stars=payment.total_amount,
        payload=payment.invoice_payload,
        telegram_charge_id=payment.telegram_payment_charge_id,
    )
    if not inserted:
        logger.info(
            "Duplicate successful payment ignored: %s",
            payment.telegram_payment_charge_id,
        )
        return

    await message.reply_text(
        "🎉 Thank You!\n\n"
        "Your donation was successful.\n\n"
        f"⭐ Amount: {payment.total_amount} Stars",
    )