"""Dynamic Telegram UI and safe direct-link delivery for media downloads."""

from __future__ import annotations

import html
import logging

from telegram import InputMediaPhoto, LabeledPrice, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes
from pymongo.errors import PyMongoError

from keyboards.inline_buttons import (
    media_downloader_keyboard,
    media_result_keyboard,
    media_result_with_hd_link_keyboard,
    tiktok_prompt_keyboard,
)
from services.telegram_stars import DONATION_CURRENCY
from services.video_downloader import (
    HD_FREE_LIMIT,
    HD_PRICE_STARS,
    VIDEO_HD_PAYMENT_PREFIX,
    VideoDownloadService,
    VideoDownloaderError,
    VideoMetadata,
    build_video_payment_payload,
    parse_video_payment_payload,
    usage_day_key,
)

logger = logging.getLogger(__name__)

MEDIA_DOWNLOADER_TEXT = (
    "🎬 Media Downloader\n\n"
    "Choose a source. Direct links are used so the bot never uploads large "
    "media files through Render."
)
TIKTOK_PROMPT_TEXT = (
    "🎵 TikTok Downloader\n\n"
    "Send a TikTok video link or a photo slideshow link."
)
ANY_LINK_PROMPT_TEXT = (
    "🔗 Any Link Downloader\n\n"
    "Send a supported public media link."
)
VIDEO_METADATA_KEY = "VIDEO_DOWNLOADER_METADATA"
VIDEO_MODE_KEY = "VIDEO_DOWNLOADER_MODE"
VIDEO_PROMPT_MESSAGE_KEY = "VIDEO_DOWNLOADER_PROMPT_MESSAGE"
VIDEO_PENDING_PAYMENT_KEY = "VIDEO_DOWNLOADER_PENDING_PAYMENT"


def _service(context: ContextTypes.DEFAULT_TYPE) -> VideoDownloadService:
    return context.application.bot_data["video_downloader"]


def _clear_video_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        VIDEO_METADATA_KEY,
        VIDEO_MODE_KEY,
        VIDEO_PROMPT_MESSAGE_KEY,
        VIDEO_PENDING_PAYMENT_KEY,
    ):
        context.user_data.pop(key, None)


def _metadata_text(metadata: VideoMetadata) -> str:
    """Render escaped metadata without exposing a long source URL in text."""

    title = html.escape(metadata.title[:180])
    details = [f"🎬 <b>{title}</b>"]
    if metadata.uploader:
        details.append(f"👤 {html.escape(metadata.uploader[:80])}")
    if metadata.duration_seconds:
        details.append(f"⏱ {metadata.duration_seconds}s")
    if metadata.photo_urls:
        details.append(f"🖼 Photo slideshow: {len(metadata.photo_urls)} images")
    details.append("\nChoose a direct stream:")
    return "\n".join(details)


async def _edit_result_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    metadata: VideoMetadata,
) -> None:
    """Edit the original prompt message, falling back to one reply if needed."""

    message = update.effective_message
    prompt = context.user_data.get(VIDEO_PROMPT_MESSAGE_KEY)
    chat_id = message.chat_id if message else None
    if isinstance(prompt, dict):
        chat_id = prompt.get("chat_id", chat_id)

    markup = media_result_keyboard(metadata)
    if chat_id and isinstance(prompt, dict) and prompt.get("message_id"):
        try:
            if metadata.thumbnail_url:
                await context.bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=prompt["message_id"],
                    media=InputMediaPhoto(
                        media=metadata.thumbnail_url,
                        caption=_metadata_text(metadata),
                        parse_mode="HTML",
                    ),
                    reply_markup=markup,
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=prompt["message_id"],
                    text=_metadata_text(metadata),
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            return
        except (BadRequest, TelegramError) as exc:
            logger.info("Could not edit downloader prompt; replying once: %s", exc)

        if metadata.thumbnail_url:
            try:
                sent = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=metadata.thumbnail_url,
                    caption=_metadata_text(metadata),
                    parse_mode="HTML",
                    reply_markup=markup,
                )
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=prompt["message_id"],
                )
                context.user_data[VIDEO_PROMPT_MESSAGE_KEY] = {
                    "chat_id": sent.chat_id,
                    "message_id": sent.message_id,
                }
                return
            except (BadRequest, TelegramError) as exc:
                logger.info("Could not send downloader thumbnail: %s", exc)

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=prompt["message_id"],
                text=_metadata_text(metadata),
                parse_mode="HTML",
                reply_markup=markup,
            )
            return
        except (BadRequest, TelegramError) as exc:
            logger.info("Could not edit downloader text prompt: %s", exc)

    if message is not None:
        sent = await message.reply_text(
            _metadata_text(metadata),
            parse_mode="HTML",
            reply_markup=markup,
        )
        context.user_data[VIDEO_PROMPT_MESSAGE_KEY] = {
            "chat_id": sent.chat_id,
            "message_id": sent.message_id,
        }


async def reply_video_downloader_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Open the downloader from the persistent main reply keyboard."""

    _clear_video_state(context)
    message = update.effective_message
    if message is not None:
        sent = await message.reply_text(
            MEDIA_DOWNLOADER_TEXT,
            reply_markup=media_downloader_keyboard(),
        )
        context.user_data[VIDEO_PROMPT_MESSAGE_KEY] = {
            "chat_id": sent.chat_id,
            "message_id": sent.message_id,
        }


async def video_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle all downloader screens and the HD unlock action."""

    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()
    action = query.data.removeprefix("video:")

    if action == "menu":
        _clear_video_state(context)
        await query.edit_message_text(
            MEDIA_DOWNLOADER_TEXT,
            reply_markup=media_downloader_keyboard(),
        )
        return
    if action == "tiktok":
        context.user_data[VIDEO_MODE_KEY] = "tiktok"
        await query.edit_message_text(
            TIKTOK_PROMPT_TEXT,
            reply_markup=tiktok_prompt_keyboard(back_callback="video:menu"),
        )
        if query.message:
            context.user_data[VIDEO_PROMPT_MESSAGE_KEY] = {
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id,
            }
        return
    if action == "coming":
        await query.edit_message_text(
            "This source is coming soon. TikTok and Any Link are available now.",
            reply_markup=media_downloader_keyboard(),
        )
        return
    if action == "any":
        context.user_data[VIDEO_MODE_KEY] = "any"
        await query.edit_message_text(
            ANY_LINK_PROMPT_TEXT,
            reply_markup=tiktok_prompt_keyboard(back_callback="video:menu"),
        )
        if query.message:
            context.user_data[VIDEO_PROMPT_MESSAGE_KEY] = {
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id,
            }
        return
    if action in {"back-main", "back"}:
        _clear_video_state(context)
        await query.edit_message_text(
            "🤖 NovaBot — Main Menu\nYour Smart Digital Assistant",
            reply_markup=None,
        )
        return
    if action == "back-tiktok":
        context.user_data.pop(VIDEO_METADATA_KEY, None)
        context.user_data[VIDEO_MODE_KEY] = "tiktok"
        await query.edit_message_text(
            TIKTOK_PROMPT_TEXT,
            reply_markup=tiktok_prompt_keyboard(back_callback="video:menu"),
        )
        return
    if action == "hd":
        await _handle_hd_request(update, context)


async def video_link_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Extract metadata for a link and edit the existing prompt message."""

    mode = context.user_data.get(VIDEO_MODE_KEY)
    message = update.effective_message
    if mode not in {"tiktok", "any"} or message is None or not message.text:
        return

    try:
        metadata = await _service(context).inspect(
            message.text,
            tiktok_only=mode == "tiktok",
        )
    except VideoDownloaderError as exc:
        await message.reply_text(
            f"Could not read that link.\n\n{exc}",
            reply_markup=tiktok_prompt_keyboard(
                back_callback="video:back-tiktok"
                if mode == "tiktok"
                else "video:menu"
            ),
        )
        return

    context.user_data[VIDEO_METADATA_KEY] = metadata
    await _edit_result_message(update, context, metadata)


async def _handle_hd_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Serve cached HD, consume free quota, or create a safe Stars invoice."""

    metadata = context.user_data.get(VIDEO_METADATA_KEY)
    user = update.effective_user
    query = update.callback_query
    if not isinstance(metadata, VideoMetadata) or user is None or query is None:
        if query:
            await query.edit_message_text(
                "This download session expired. Please send the link again.",
                reply_markup=media_downloader_keyboard(),
            )
        return

    store = _service(context).store
    if store is None:
        await query.edit_message_text(
            "HD downloads are temporarily unavailable because MongoDB is not configured.",
            reply_markup=tiktok_prompt_keyboard(),
        )
        return

    try:
        # The extraction already happened before the invoice. This means an API
        # error cannot occur after payment is approved.
        metadata = await _service(context).prepare_hd(metadata)
        cached = store.get_cache(metadata.cache_key)
        if cached is None:
            raise VideoDownloaderError("The cached stream expired. Please send the link again.")

        if store.claim_free_hd(user.id, user.username, usage_day_key()):
            await query.edit_message_text(
                "✅ Your free HD stream is ready.",
                reply_markup=media_result_with_hd_link_keyboard(metadata),
            )
            return

        payload = build_video_payment_payload(user.id, metadata.cache_key)
        await context.bot.send_invoice(
            chat_id=query.message.chat_id if query.message else user.id,
            title="HD Media Download",
            description="Unlock one HD direct stream with 1 Telegram Star.",
            payload=payload,
            provider_token="",
            currency=DONATION_CURRENCY,
            prices=[LabeledPrice(label="HD direct stream", amount=HD_PRICE_STARS)],
        )
        context.user_data[VIDEO_PENDING_PAYMENT_KEY] = {
            "cache_key": metadata.cache_key,
            "message_id": query.message.message_id if query.message else None,
        }
        await query.edit_message_text(
            f"🌟 You have used your {HD_FREE_LIMIT} free HD downloads today.\n\n"
            "Pay 1 Telegram Star to unlock this HD direct stream.",
            reply_markup=tiktok_prompt_keyboard(back_callback="video:menu"),
        )
    except (VideoDownloaderError, PyMongoError, TelegramError) as exc:
        logger.warning("Could not prepare HD download: %s", exc)
        await query.edit_message_text(
            "We could not prepare the HD stream, so no payment was requested. "
            "Please try again.",
            reply_markup=tiktok_prompt_keyboard(back_callback="video:menu"),
        )


async def video_pre_checkout_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Approve only one-Star HD invoices whose cached URL still exists."""

    query = update.pre_checkout_query
    if query is None or not query.invoice_payload.startswith(VIDEO_HD_PAYMENT_PREFIX):
        return False

    parsed = parse_video_payment_payload(query.invoice_payload)
    store = _service(context).store
    valid = (
        parsed is not None
        and query.currency == DONATION_CURRENCY
        and query.total_amount == HD_PRICE_STARS
        and query.from_user.id == parsed[0]
        and store is not None
        and store.get_cache(parsed[1]) is not None
    )
    await query.answer(
        ok=valid,
        error_message=None if valid else "This HD stream expired. No Stars were charged.",
    )
    return True


async def payment_pre_checkout_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Route Telegram's single pre-checkout update stream safely."""

    query = update.pre_checkout_query
    if query is not None and query.invoice_payload.startswith(VIDEO_HD_PAYMENT_PREFIX):
        await video_pre_checkout_handler(update, context)
        return

    from handlers.donation import pre_checkout_handler

    await pre_checkout_handler(update, context)


async def successful_payment_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Route donation and downloader payment updates without handler races."""

    message = update.effective_message
    payment = message.successful_payment if message else None
    if payment is not None and payment.invoice_payload.startswith(VIDEO_HD_PAYMENT_PREFIX):
        await video_successful_payment_handler(update, context)
        return

    from handlers.donation import successful_payment_handler

    await successful_payment_handler(update, context)


async def video_successful_payment_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Deliver a paid URL, refunding if a post-payment safety check fails."""

    message = update.effective_message
    payment = message.successful_payment if message else None
    if payment is None or not payment.invoice_payload.startswith(VIDEO_HD_PAYMENT_PREFIX):
        return False

    user = update.effective_user
    parsed = parse_video_payment_payload(payment.invoice_payload)
    store = _service(context).store
    cache = store.get_cache(parsed[1]) if parsed and store is not None else None
    if user is None or parsed is None or parsed[0] != user.id or cache is None:
        try:
            await context.bot.refund_star_payment(
                user_id=user.id if user else 0,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
        except TelegramError:
            logger.exception("Could not refund a paid HD invoice after cache failure.")
        if message:
            await message.reply_text(
                "The HD stream expired before delivery. The 1 Star payment was refunded "
                "automatically when Telegram allowed it."
            )
        return True

    if not store.record_payment(
        user_id=user.id,
        cache_key=parsed[1],
        telegram_charge_id=payment.telegram_payment_charge_id,
    ):
        logger.info("Duplicate paid video payment ignored.")
        return True

    metadata = VideoMetadata(
        normalized_url=str(cache["normalized_url"]),
        cache_key=str(cache["cache_key"]),
        title=str(cache.get("title") or "Media"),
        thumbnail_url=cache.get("thumbnail_url"),
        normal_url=str(cache.get("normal_url") or ""),
        hd_url=str(cache.get("hd_url") or ""),
        duration_seconds=cache.get("duration_seconds"),
        uploader=cache.get("uploader"),
        photo_urls=tuple(cache.get("photo_urls") or ()),
    )
    if message:
        await message.reply_text(
            "✅ Payment received. Your HD direct stream is ready.",
            reply_markup=media_result_with_hd_link_keyboard(metadata),
        )
    return True