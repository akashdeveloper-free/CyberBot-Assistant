"""CyberBot application entry point."""

from __future__ import annotations

from telegram.error import InvalidToken
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from config.settings import Settings, load_settings
from database.database import Database
from handlers.donation import (
    custom_amount_message_handler,
    donation_callback_handler,
    pre_checkout_handler,
    successful_payment_handler,
)
from handlers.menu import menu_callback_handler
from handlers.start import start_handler
from utils.logger import logger


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Log unexpected failures and give the user a safe response."""

    error = context.error
    logger.error("Unhandled Telegram update error: %r", error, exc_info=error)

    if not isinstance(update, Update):
        return

    try:
        if update.callback_query is not None:
            await update.callback_query.answer(
                "Something went wrong. Please try again.",
                show_alert=True,
            )
        elif update.effective_message is not None:
            await update.effective_message.reply_text(
                "Something went wrong while processing your request. "
                "Please try again."
            )
    except Exception:
        logger.exception("Could not send the user-facing error message.")


def build_application(settings: Settings) -> Application:
    """Build the Telegram application with modular handlers."""

    database = Database(settings.database_path)
    application = Application.builder().token(settings.bot_token).build()
    application.bot_data["database"] = database

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(
        CallbackQueryHandler(menu_callback_handler, pattern=r"^(menu:|future:)")
    )
    application.add_handler(
        CallbackQueryHandler(donation_callback_handler, pattern=r"^donate:")
    )
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, custom_amount_message_handler)
    )
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    """Start CyberBot in long-polling mode."""

    try:
        settings = load_settings()
        application = build_application(settings)
        logger.info("CyberBot is starting in polling mode.")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except InvalidToken:
        logger.error(
            "CyberBot could not authenticate with Telegram. "
            "Check that BOT_TOKEN is a valid BotFather token."
        )
        raise RuntimeError("Telegram bot authentication failed.") from None
    except (RuntimeError, KeyboardInterrupt):
        raise
    except Exception:
        logger.exception("CyberBot stopped because of an unexpected startup error.")
        raise


if __name__ == "__main__":
    main()
