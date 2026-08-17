"""Telegram flow for the isolated provider-driven video downloader."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.donation import (
    custom_amount_message_handler,
    pre_checkout_handler,
    successful_payment_handler,
)
from services.video_downloader import (
    DownloadError,
    DownloadRequest,
    FormatOption,
    Platform,
    VideoDownloaderService,
    VideoMetadata,
)
from services.video_downloader.payment import (
    build_video_payment_payload,
    create_video_4k_invoice,
    is_video_payment_payload,
    parse_video_payment_payload,
    VIDEO_4K_STARS,
    validate_video_pre_checkout,
)
from services.telegram_stars import DONATION_CURRENCY

logger = logging.getLogger(__name__)

VIDEO_PLATFORM_KEY = "VIDEO_DOWNLOADER_PLATFORM"
VIDEO_METADATA_KEY = "VIDEO_DOWNLOADER_METADATA"
VIDEO_PENDING_KEY = "VIDEO_DOWNLOADER_PENDING"
VIDEO_BUSY_KEY = "VIDEO_DOWNLOADER_BUSY"

PLATFORM_TEXT = (
    "🎬 Video Downloader\n\n"
    "Choose a platform, then send a public link."
)


def _service(context: ContextTypes.DEFAULT_TYPE) -> VideoDownloaderService:
    service = context.application.bot_data.get("video_downloader")
    if isinstance(service, VideoDownloaderService):
        return service
    return VideoDownloaderService.from_default_environment()


def _platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("YouTube", callback_data="video:platform:youtube"),
                InlineKeyboardButton("TikTok", callback_data="video:platform:tiktok"),
            ],
            [
                InlineKeyboardButton("Facebook", callback_data="video:platform:facebook"),
                InlineKeyboardButton("Any Link", callback_data="video:platform:any"),
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="video:back_main")],
        ]
    )


def _url_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Back", callback_data="video:platforms")]]
    )


def _download_keyboard(link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Download Now", url=link)]]
    )


def _quality_keyboard(metadata: VideoMetadata) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(option.label, callback_data=f"video:quality:{option.option_id}")]
        for option in metadata.options
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="video:url")])
    return InlineKeyboardMarkup(rows)


def _payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Pay ⭐5", callback_data="video:pay4k")],
            [InlineKeyboardButton("⬅️ Back", callback_data="video:quality")],
        ]
    )


def _platform(value: str | None) -> Platform | None:
    try:
        return Platform(value) if value else None
    except ValueError:
        return None


def _clear_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        VIDEO_PLATFORM_KEY,
        VIDEO_METADATA_KEY,
        VIDEO_PENDING_KEY,
        VIDEO_BUSY_KEY,
    ):
        context.user_data.pop(key, None)


def clear_video_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Public cleanup hook for routing/tests; it never touches the database."""

    _clear_state(context)


async def video_downloader_start_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    if message is None:
        return
    _clear_state(context)
    await message.reply_text(PLATFORM_TEXT, reply_markup=_platform_keyboard())


async def video_downloader_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    action = query.data

    if action == "video:back_main":
        _clear_state(context)
        await query.edit_message_text(
            "🤖 NovaBot — Main Menu\nYour Smart Digital Assistant",
            reply_markup=None,
        )
        return
    if action == "video:platforms":
        _clear_state(context)
        await query.edit_message_text(PLATFORM_TEXT, reply_markup=_platform_keyboard())
        return
    if action.startswith("video:platform:"):
        selected = _platform(action.rsplit(":", 1)[-1])
        if selected is None:
            await query.edit_message_text(PLATFORM_TEXT, reply_markup=_platform_keyboard())
            return
        context.user_data[VIDEO_PLATFORM_KEY] = selected.value
        context.user_data.pop(VIDEO_METADATA_KEY, None)
        platform_label = {
            Platform.YOUTUBE: "YouTube",
            Platform.TIKTOK: "TikTok",
            Platform.FACEBOOK: "Facebook",
            Platform.ANY: "Any Link",
        }[selected]
        await query.edit_message_text(
            f"{platform_label} Downloader\n\nSend the video URL to continue.",
            reply_markup=_url_keyboard(),
        )
        return
    if action == "video:url":
        metadata = context.user_data.get(VIDEO_METADATA_KEY)
        if isinstance(metadata, VideoMetadata):
            await query.edit_message_text(
                "Send another public URL to continue.", reply_markup=_url_keyboard()
            )
        else:
            await query.edit_message_text(PLATFORM_TEXT, reply_markup=_platform_keyboard())
        return
    if action == "video:quality":
        metadata = context.user_data.get(VIDEO_METADATA_KEY)
        if isinstance(metadata, VideoMetadata):
            await query.edit_message_text(
                f"Metadata ready: {metadata.title}\n\nChoose a quality or format.",
                reply_markup=_quality_keyboard(metadata),
            )
        else:
            await query.edit_message_text(PLATFORM_TEXT, reply_markup=_platform_keyboard())
        return
    if action == "video:pay4k":
        await _send_4k_invoice(query, context)
        return
    if action.startswith("video:quality:"):
        await _quality_selected(query, context, action.rsplit(":", 1)[-1])


async def _quality_selected(query, context, option_id: str) -> None:
    metadata = context.user_data.get(VIDEO_METADATA_KEY)
    platform = _platform(context.user_data.get(VIDEO_PLATFORM_KEY))
    if not isinstance(metadata, VideoMetadata) or platform is None:
        await query.edit_message_text(PLATFORM_TEXT, reply_markup=_platform_keyboard())
        return
    option = next((item for item in metadata.options if item.option_id == option_id), None)
    if option is None:
        await query.edit_message_text(
            "That format is no longer available.", reply_markup=_quality_keyboard(metadata)
        )
        return
    request = DownloadRequest(
        request_id=VideoDownloaderService.new_request_id(),
        user_id=(
            getattr(getattr(query, "from_user", None), "id", None)
            or query.message.chat.id
        ),
        platform=platform,
        source_url=metadata.source_url,
        option_id=option.option_id,
    )
    context.user_data[VIDEO_PENDING_KEY] = (request, metadata, option)
    if option.is_4k:
        await query.edit_message_text(
            "4K delivery requires a one-time payment of 5 Telegram Stars.\n\n"
            "After successful payment, your temporary download link will be sent.",
            reply_markup=_payment_keyboard(),
        )
        return
    await _deliver(query.message, context, request, metadata, option)


async def _send_4k_invoice(query, context) -> None:
    pending = context.user_data.get(VIDEO_PENDING_KEY)
    if not isinstance(pending, tuple) or len(pending) not in {3, 4}:
        await query.edit_message_text(PLATFORM_TEXT, reply_markup=_platform_keyboard())
        return
    if len(pending) == 4:
        await query.answer("The 4K payment invoice is already open.")
        return
    request, _, option = pending
    if not isinstance(request, DownloadRequest) or not isinstance(option, FormatOption):
        await query.edit_message_text(PLATFORM_TEXT, reply_markup=_platform_keyboard())
        return
    if not option.is_4k or query.message is None:
        return
    payload = build_video_payment_payload(query.message.chat.id, request.request_id)
    context.user_data[VIDEO_PENDING_KEY] = (request, pending[1], option, payload)
    try:
        await create_video_4k_invoice(context.bot, query.message.chat.id, payload)
    except Exception:
        logger.exception("Could not create the 4K invoice.")
        await query.edit_message_text(
            "The 4K payment could not be started. Please try again.",
            reply_markup=_payment_keyboard(),
        )


async def _deliver(message, context, request, metadata, option) -> None:
    if message is None:
        return
    if context.user_data.get(VIDEO_BUSY_KEY):
        await message.reply_text("This request is already being prepared.")
        return
    context.user_data[VIDEO_BUSY_KEY] = True
    try:
        link = await _service(context).prepare_delivery(request, metadata, option)
        await message.reply_text(
            "✅ Your download is ready.\n\n"
            "The secure link expires soon. NovaBot does not store the video.",
            reply_markup=_download_keyboard(link),
        )
    except DownloadError as exc:
        await message.reply_text(
            str(exc) if str(exc) else "The download could not be prepared safely.",
            reply_markup=_quality_keyboard(metadata),
        )
    except Exception:
        logger.exception("Downloader request failed.")
        await message.reply_text(
            "The download could not be prepared safely.",
            reply_markup=_quality_keyboard(metadata),
        )
    finally:
        context.user_data.pop(VIDEO_BUSY_KEY, None)
        context.user_data.pop(VIDEO_PENDING_KEY, None)


async def video_downloader_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route text to downloader only when a downloader URL is expected."""

    if VIDEO_PLATFORM_KEY not in context.user_data:
        await custom_amount_message_handler(update, context)
        return
    message = update.effective_message
    platform = _platform(context.user_data.get(VIDEO_PLATFORM_KEY))
    if message is None or platform is None:
        return
    try:
        metadata = await _service(context).inspect(
            platform=platform,
            user_id=message.chat.id,
            source_url=message.text or "",
        )
        context.user_data[VIDEO_METADATA_KEY] = metadata
        await message.reply_text(
            f"Metadata ready: {metadata.title}\n\nChoose a quality or format.",
            reply_markup=_quality_keyboard(metadata),
        )
    except DownloadError as exc:
        await message.reply_text(str(exc), reply_markup=_url_keyboard())
    except Exception:
        logger.exception("Downloader metadata lookup failed.")
        await message.reply_text(
            "The link could not be inspected safely. Please try another URL.",
            reply_markup=_url_keyboard(),
        )


async def video_pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if query is None or not is_video_payment_payload(query.invoice_payload):
        await pre_checkout_handler(update, context)
        return
    ok, error = validate_video_pre_checkout(
        query.currency, query.total_amount, query.invoice_payload
    )
    await query.answer(ok=ok, error_message=error)


async def video_successful_payment_router(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    payment = message.successful_payment if message else None
    payload = payment.invoice_payload if payment else None
    if not is_video_payment_payload(payload):
        await successful_payment_handler(update, context)
        return
    parsed = parse_video_payment_payload(payload or "")
    user = update.effective_user
    pending = context.user_data.get(VIDEO_PENDING_KEY)
    if (
        parsed is None
        or user is None
        or message is None
        or parsed[0] != message.chat.id
    ):
        await message.reply_text("This 4K payment request is no longer valid.")
        return
    if payment is None:
        await message.reply_text("This 4K payment request is no longer valid.")
        return
    payment_ok, payment_error = validate_video_pre_checkout(
        payment.currency,
        payment.total_amount,
        payment.invoice_payload,
    )
    if not payment_ok:
        await message.reply_text(payment_error or "This 4K payment request is no longer valid.")
        return
    if not isinstance(pending, tuple) or len(pending) < 3:
        await message.reply_text("Payment received, but the download request expired.")
        return
    request, metadata, option = pending[:3]
    if (
        not isinstance(request, DownloadRequest)
        or request.request_id != parsed[1]
        or request.user_id != user.id
        or payment.currency != DONATION_CURRENCY
        or payment.total_amount != VIDEO_4K_STARS
    ):
        await message.reply_text("Payment received, but the download request expired.")
        return
    await _deliver(message, context, request, metadata, option)