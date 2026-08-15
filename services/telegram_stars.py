"""Telegram Stars invoice and payment validation service."""

from __future__ import annotations

from telegram import Bot, LabeledPrice

DONATION_CURRENCY = "XTR"
DONATION_PAYLOAD_PREFIX = "cyberbot:donation:"
PROVIDER_TOKEN = ""


def build_donation_payload(chat_id: int, stars: int) -> str:
    """Build a traceable payload without storing sensitive data."""

    return f"{DONATION_PAYLOAD_PREFIX}{chat_id}:{stars}"


async def create_invoice(
    bot: Bot,
    chat_id: int,
    stars: int,
    payload: str,
) -> None:
    """Send a Telegram Stars invoice using the required XTR configuration."""

    await bot.send_invoice(
        chat_id=chat_id,
        title="CyberBot Donation",
        description=f"Support CyberBot with {stars} Telegram Stars.",
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=DONATION_CURRENCY,
        prices=[LabeledPrice(label=f"{stars} Stars", amount=stars)],
    )


def validate_pre_checkout(
    currency: str,
    total_amount: int,
    invoice_payload: str,
) -> tuple[bool, str | None]:
    """Validate the fields that must match a CyberBot Stars donation."""

    if currency != DONATION_CURRENCY:
        return False, "This payment uses an unsupported currency."
    if total_amount < 1:
        return False, "The donation amount must be at least 1 Star."
    if not invoice_payload.startswith(DONATION_PAYLOAD_PREFIX):
        return False, "This payment request is no longer valid."
    return True, None