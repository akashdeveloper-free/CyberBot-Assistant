"""NovaBot application entry point."""

from __future__ import annotations

import asyncio
import signal
from threading import Lock

from telegram import BotCommand, MenuButtonCommands, Update
from telegram.error import Conflict, InvalidToken
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
from handlers.menu import reply_menu_handler
from handlers.start import start_handler
from services.health_server import HealthServer
from services.polling_lock import (
    PollingAlreadyRunningError,
    PollingInstanceLock,
)
from utils.logger import logger


_polling_run_guard = Lock()
_polling_run_active = False


def _claim_polling_run() -> None:
    """Prevent two polling lifecycles from sharing one process."""

    global _polling_run_active
    with _polling_run_guard:
        if _polling_run_active:
            raise RuntimeError("NovaBot polling has already been started in this process.")
        _polling_run_active = True


def _release_polling_run() -> None:
    """Allow a fully shut down process lifecycle to be tested or restarted."""

    global _polling_run_active
    with _polling_run_guard:
        _polling_run_active = False


def _polling_error_callback(
    stop_event: asyncio.Event,
    conflict_event: asyncio.Event,
):
    """Stop cleanly when Telegram reports another active getUpdates owner."""

    def handle(error: Exception) -> None:
        if isinstance(error, Conflict):
            logger.error(
                "Telegram rejected polling because another process owns getUpdates. "
                "Stopping this instance for a clean handoff."
            )
            conflict_event.set()
            stop_event.set()
            return

        logger.error("Telegram polling error: %r", error, exc_info=error)

    return handle


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
            BotCommand("start", "Open NovaBot"),
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
        MessageHandler(
            filters.Regex(
                r"^(?:📁 File Tools|🔐 Security Tools|"
                r"⚙️ Settings|⭐ Donate Stars|ℹ️ Help|🎬 Video Downloader)$"
            ),
            reply_menu_handler,
        )
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
    """Run one guarded polling instance with explicit shutdown ordering."""

    _claim_polling_run()
    stop_event = asyncio.Event()
    conflict_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    signal_handlers_installed = False
    updater = application.updater

    try:
        if updater is None:
            raise RuntimeError("Telegram updater is not available.")
        if application.running or updater.running:
            raise RuntimeError("NovaBot application or polling is already running.")

        for signum in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(signum, stop_event.set)
                signal_handlers_installed = True
            except (NotImplementedError, RuntimeError):
                logger.warning("Could not install handler for signal %s.", signum)

        await application.initialize()
        if application.post_init is not None:
            await application.post_init(application)
        await application.bot.delete_webhook(drop_pending_updates=False)
        logger.info("Telegram webhook cleared before polling.")
        await application.start()
        try:
            await updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=False,
                bootstrap_retries=-1,
                error_callback=_polling_error_callback(stop_event, conflict_event),
            )
        except Conflict:
            logger.error(
                "Telegram rejected polling because another process owns getUpdates. "
                "Stopping this instance for a clean handoff."
            )
            conflict_event.set()
            stop_event.set()
            raise
        logger.info("NovaBot polling is active.")
        await stop_event.wait()
        if conflict_event.is_set():
            raise RuntimeError(
                "Telegram polling stopped because another process owns getUpdates."
            )
    finally:
        try:
            if updater is not None and updater.running:
                logger.info("Stopping Telegram polling.")
                await updater.stop()
        finally:
            try:
                if application.running:
                    await application.stop()
            finally:
                try:
                    try:
                        if application.post_shutdown is not None:
                            await application.post_shutdown(application)
                    finally:
                        await application.shutdown()
                finally:
                    if signal_handlers_installed:
                        for signum in (signal.SIGTERM, signal.SIGINT):
                            try:
                                loop.remove_signal_handler(signum)
                            except Exception:
                                logger.exception(
                                    "Could not remove handler for signal %s.",
                                    signum,
                                )
                    try:
                        health_server.stop()
                    finally:
                        _release_polling_run()


def main() -> None:
    """Start the HTTP health server and Telegram long polling together."""

    health_server: HealthServer | None = None
    polling_lock = PollingInstanceLock()
    try:
        settings = load_settings()
        polling_lock.acquire()
        application = build_application(settings)
        health_server = HealthServer(settings.port)
        health_server.start()
        logger.info("NovaBot health server is listening on port %s.", settings.port)
        asyncio.run(run_application(application, health_server))
    except PollingAlreadyRunningError as exc:
        logger.error(
            "A second NovaBot process was refused because polling is already active."
        )
        raise RuntimeError("Another NovaBot polling process is already running.") from exc
    except InvalidToken:
        logger.error(
            "NovaBot could not authenticate with Telegram. "
            "Check that BOT_TOKEN is a valid BotFather token."
        )
        raise RuntimeError("Telegram bot authentication failed.") from None
    except (RuntimeError, KeyboardInterrupt):
        raise
    except Exception:
        logger.exception("NovaBot stopped because of an unexpected startup error.")
        raise
    finally:
        try:
            if health_server is not None:
                health_server.stop()
        finally:
            polling_lock.release()


if __name__ == "__main__":
    main()
