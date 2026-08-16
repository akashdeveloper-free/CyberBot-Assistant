"""4K Stars contract layered on the existing XTR payment configuration."""

from __future__ import annotations

from telegram import Bot, LabeledPrice
from services.telegram_stars import DONATION_CURRENCY, PROVIDER_TOKEN


VIDEO_4K_STARS = 5
VIDEO_PAYMENT_PAYLOAD_PREFIX = "cyberbot:video4k:"


def build_video_payment_payload(chat_id: int, request_id: str) -> str:
    """Bind a 4K invoice to the current Telegram chat and request."""

    return f"{VIDEO_PAYMENT_PAYLOAD_PREFIX}{chat_id}:{request_id}"


def validate_video_pre_checkout(
    currency: str,
    total_amount: int,
    invoice_payload: str,
) -> tuple[bool, str | None]:
    if currency != DONATION_CURRENCY:
        return False, "This payment uses an unsupported currency."
    if total_amount != VIDEO_4K_STARS:
        return False, "This 4K payment request is no longer valid."
    parts = invoice_payload.split(":")
    if len(parts) != 4 or parts[0] != "cyberbot" or parts[1] != "video4k":
        return False, "This 4K payment request is no longer valid."
    try:
        if int(parts[2]) < 1 or not parts[3]:
            raise ValueError
    except ValueError:
        return False, "This 4K payment request is no longer valid."
    return True, None


async def create_video_4k_invoice(bot: Bot, chat_id: int, payload: str) -> None:
    await bot.send_invoice(
        chat_id=chat_id,
        title="NovaBot 4K Download",
        description="Unlock one 4K video download.",
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=DONATION_CURRENCY,
        prices=[LabeledPrice(label="4K Download", amount=VIDEO_4K_STARS)],
    )


def is_video_payment_payload(payload: str | None) -> bool:
    return bool(payload and payload.startswith(VIDEO_PAYMENT_PAYLOAD_PREFIX))


def parse_video_payment_payload(payload: str) -> tuple[int, str] | None:
    if not is_video_payment_payload(payload):
        return None
    parts = payload.split(":")
    if len(parts) != 4:
        return None
    try:
        chat_id = int(parts[2])
    except ValueError:
        return None
    return chat_id, parts[3]