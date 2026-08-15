"""CyberBot application entry point."""

from __future__ import annotations

import asyncio
import signal

from telegram import BotCommand, MenuButtonCommands, Update
from telegram.error import InvalidToken
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
from handlers.commands import help_handler, settings_handler
from handlers.donation import (
    custom_amount_message_handler,
    donate_command_handler,
    donation_callback_handler,
    pre_checkout_handler,
    successful_payment_handler,
)
from handlers.menu import menu_callback_handler
from handlers.start import start_handler
from services.health_server import HealthServer
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


async def post_init(application: Application) -> None:
    """Configure Telegram's command list and menu button after initialization."""

    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open CyberBot"),
            BotCommand("donate", "⭐ Donate Stars"),
            BotCommand("help", "Get help"),
            BotCommand("settings", "Open settings"),
        ]
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Telegram command menu configured.")


async def post_shutdown(application: Application) -> None:
    """Close application-owned resources during every shutdown path."""

    database = application.bot_data.pop("database", None)
    if isinstance(database, Database):
        database.close()


def build_application(settings: Settings) -> Application:
    """Build the Telegram application with modular handlers."""

    database = Database(settings.database_path)
    application = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["database"] = database

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("donate", donate_command_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("settings", settings_handler))
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


async def run_application(
    application: Application,
    health_server: HealthServer,
) -> None:
    """Run exactly one polling instance with explicit shutdown ordering."""

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    signal_handlers_installed = False
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop_event.set)
            signal_handlers_installed = True
        except (NotImplementedError, RuntimeError):
            logger.warning("Could not install handler for signal %s.", signum)

    initialized = False
    started = False
    polling = False
    updater = application.updater
    if updater is None:
        raise RuntimeError("Telegram updater is not available.")

    try:
        await application.initialize()
        initialized = True
        if application.post_init is not None:
            await application.post_init(application)
        await application.start()
        started = True
        await updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
            bootstrap_retries=-1,
        )
        polling = True
        logger.info("CyberBot polling is active.")
        await stop_event.wait()
    finally:
        if polling and updater.running:
            logger.info("Stopping Telegram polling.")
            await updater.stop()
        if started:
            await application.stop()
        if initialized:
            if application.post_shutdown is not None:
                await application.post_shutdown(application)
            await application.shutdown()
        if signal_handlers_installed:
            for signum in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(signum)
        health_server.stop()


def main() -> None:
    """Start the HTTP health server and Telegram long polling together."""

    health_server: HealthServer | None = None
    try:
        settings = load_settings()
        application = build_application(settings)
        health_server = HealthServer(settings.port)
        health_server.start()
        logger.info("CyberBot health server is listening on port %s.", settings.port)
        asyncio.run(run_application(application, health_server))
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
    finally:
        if health_server is not None:
            health_server.stop()


if __name__ == "__main__":
    main()
