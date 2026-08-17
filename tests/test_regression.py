"""Regression coverage for NovaBot's protected core and donation navigation."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import Conflict

from database.database import Database
from handlers.donation import (
    DONATION_MENU_TEXT,
    PENDING_DONATION_AMOUNT,
    WAITING_FOR_CUSTOM_STARS,
    custom_amount_message_handler,
    donation_callback_handler,
    donate_command_handler,
    pre_checkout_handler,
    successful_payment_handler,
)
from handlers.menu import menu_callback_handler, reply_menu_handler
from handlers.start import WELCOME_TEXT, start_handler
from keyboards.reply_keyboard import (
    DONATE_STARS_BUTTON,
    VIDEO_DOWNLOADER_BUTTON,
    main_reply_keyboard,
)
from main import (
    _claim_polling_run,
    _polling_error_callback,
    _release_polling_run,
    post_shutdown,
    run_application,
)
from services.health_server import HealthServer, create_health_app
from services.polling_lock import PollingAlreadyRunningError, PollingInstanceLock
from services.telegram_stars import validate_pre_checkout


def _button(markup, text: str):
    return next(
        button
        for row in markup.inline_keyboard
        for button in row
        if button.text == text
    )


def _context(database: Database | None = None):
    database = database or MagicMock()
    return SimpleNamespace(
        user_data={},
        bot=MagicMock(),
        application=SimpleNamespace(bot_data={"database": database}),
    )


def _callback_update(data: str, message=None):
    query = SimpleNamespace(
        data=data,
        message=message or SimpleNamespace(chat=SimpleNamespace(id=123)),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    return SimpleNamespace(callback_query=query), query


class DonationNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_and_donate_menu(self):
        database = MagicMock()
        context = _context(database)
        user = SimpleNamespace(id=7, username="donor")
        start_message = MagicMock()
        start_message.reply_text = AsyncMock()
        start_update = SimpleNamespace(
            effective_user=user,
            effective_message=start_message,
        )

        await start_handler(start_update, context)

        database.ensure_user.assert_called_once_with(7, "donor")
        self.assertEqual(start_message.reply_text.call_args.args[0], WELCOME_TEXT)
        self.assertIsNotNone(start_message.reply_text.call_args.kwargs["reply_markup"])
        self.assertEqual(main_reply_keyboard().keyboard, start_message.reply_text.call_args.kwargs["reply_markup"].keyboard)

        donate_message = MagicMock()
        donate_message.reply_text = AsyncMock()
        await donate_command_handler(
            SimpleNamespace(effective_message=donate_message),
            context,
        )

        self.assertEqual(donate_message.reply_text.call_args.args[0], DONATION_MENU_TEXT)
        markup = donate_message.reply_text.call_args.kwargs["reply_markup"]
        self.assertEqual(
            [button.text for row in markup.inline_keyboard for button in row],
            ["⭐ 10 Stars", "⭐ 50 Stars", "⭐ 100 Stars", "✏ Custom Stars Amount", "⬅️ Back"],
        )

    async def test_fixed_amount_confirmation_has_pay_and_back_to_donation(self):
        context = _context()
        update, query = _callback_update("donate:10")

        await donation_callback_handler(update, context)

        self.assertEqual(context.user_data[PENDING_DONATION_AMOUNT], 10)
        markup = query.edit_message_text.call_args.kwargs["reply_markup"]
        self.assertEqual(_button(markup, "⭐ Pay").callback_data, "donate:continue")
        self.assertEqual(_button(markup, "⬅️ Back").callback_data, "menu:donate")

    async def test_custom_amount_uses_same_confirmation_screen(self):
        database = MagicMock()
        context = _context(database)
        context.user_data[WAITING_FOR_CUSTOM_STARS] = True
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.text = "25"
        message.chat_id = 123
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=7, username="donor"),
        )

        with patch("handlers.donation.create_invoice", new=AsyncMock()) as create_invoice:
            await custom_amount_message_handler(update, context)

        database.ensure_user.assert_called_once_with(7, "donor")
        create_invoice.assert_not_awaited()
        self.assertFalse(context.user_data[WAITING_FOR_CUSTOM_STARS])
        self.assertEqual(context.user_data[PENDING_DONATION_AMOUNT], 25)
        markup = message.reply_text.call_args.kwargs["reply_markup"]
        self.assertEqual(_button(markup, "⭐ Pay").callback_data, "donate:continue")
        self.assertEqual(_button(markup, "⬅️ Back").callback_data, "menu:donate")

    async def test_back_from_confirmation_returns_to_donation_menu(self):
        context = _context()
        context.user_data[WAITING_FOR_CUSTOM_STARS] = True
        context.user_data[PENDING_DONATION_AMOUNT] = 25
        update, query = _callback_update("menu:donate")

        await menu_callback_handler(update, context)

        self.assertNotIn(WAITING_FOR_CUSTOM_STARS, context.user_data)
        self.assertNotIn(PENDING_DONATION_AMOUNT, context.user_data)
        self.assertEqual(
            query.edit_message_text.call_args.kwargs["text"],
            DONATION_MENU_TEXT,
        )
        self.assertEqual(
            query.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard[-1][0].callback_data,
            "menu:main",
        )

    async def test_pay_callback_creates_invoice_and_clears_pending_amount(self):
        context = _context()
        context.user_data[PENDING_DONATION_AMOUNT] = 50
        message = SimpleNamespace(chat=SimpleNamespace(id=123))
        update, query = _callback_update("donate:continue", message)

        with patch("handlers.donation.create_invoice", new=AsyncMock()) as create_invoice:
            await donation_callback_handler(update, context)

        create_invoice.assert_awaited_once()
        self.assertNotIn(PENDING_DONATION_AMOUNT, context.user_data)
        self.assertEqual(
            query.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard[-1][0].callback_data,
            "menu:donate",
        )

    async def test_invalid_custom_amount_keeps_back_to_donation(self):
        context = _context()
        context.user_data[WAITING_FOR_CUSTOM_STARS] = True
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.text = "not-a-number"
        update = SimpleNamespace(effective_message=message)

        await custom_amount_message_handler(update, context)

        markup = message.reply_text.call_args.kwargs["reply_markup"]
        self.assertEqual(_button(markup, "⬅️ Back").callback_data, "menu:donate")


class PaymentAndDatabaseTests(unittest.IsolatedAsyncioTestCase):
    def test_stars_validation(self):
        self.assertEqual(
            validate_pre_checkout("XTR", 10, "cyberbot:donation:123:10"),
            (True, None),
        )
        for args in (
            ("USD", 10, "cyberbot:donation:123:10"),
            ("XTR", 0, "cyberbot:donation:123:0"),
            ("XTR", 10, "other:123:10"),
            ("XTR", 11, "cyberbot:donation:123:10"),
        ):
            self.assertFalse(validate_pre_checkout(*args)[0])

    async def test_pre_checkout_and_successful_payment_handlers(self):
        context = _context()
        pre_checkout = SimpleNamespace(
            currency="XTR",
            total_amount=10,
            invoice_payload="cyberbot:donation:123:10",
            answer=AsyncMock(),
        )
        await pre_checkout_handler(SimpleNamespace(pre_checkout_query=pre_checkout), context)
        pre_checkout.answer.assert_awaited_once_with(ok=True, error_message=None)

        context.application.bot_data["database"].record_donation.return_value = True
        message = SimpleNamespace(
            successful_payment=SimpleNamespace(
                invoice_payload="cyberbot:donation:123:10",
                total_amount=10,
                telegram_payment_charge_id="charge-1",
            ),
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=7, username="donor"),
        )
        await successful_payment_handler(update, context)
        message.reply_text.assert_awaited_once()

    def test_database_schema_totals_and_duplicate_charge(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.sqlite3")
            database.ensure_user(7, "donor")
            self.assertTrue(
                database.record_donation(
                    7, "donor", 10, "cyberbot:donation:7:10", "charge-1"
                )
            )
            self.assertFalse(
                database.record_donation(
                    7, "donor", 10, "cyberbot:donation:7:10", "charge-1"
                )
            )
            with database._connect() as connection:
                row = connection.execute(
                    "SELECT total_stars, usage_count FROM users WHERE user_id = 7"
                ).fetchone()
            self.assertEqual(dict(row), {"total_stars": 10, "usage_count": 1})
            database.close()


class LifecycleAndHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_server_and_routes(self):
        client = create_health_app().test_client()
        self.assertEqual(client.get("/").status_code, 200)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

        server = HealthServer(0)
        server.start()
        server.stop()
        server.stop()

    def test_polling_lock_and_error_callback(self):
        lock = PollingInstanceLock()
        other_lock = PollingInstanceLock()
        try:
            lock.acquire()
            with self.assertRaises(PollingAlreadyRunningError):
                other_lock.acquire()
        finally:
            lock.release()
            other_lock.release()

        first = asyncio.Event()
        second = asyncio.Event()
        _polling_error_callback(first, second)(Exception("ordinary"))
        self.assertFalse(first.is_set())
        _polling_error_callback(first, second)(Conflict("duplicate polling"))
        self.assertTrue(first.is_set())
        self.assertTrue(second.is_set())

    async def test_run_application_orders_webhook_polling_and_shutdown(self):
        events: list[str] = []
        application = MagicMock()
        application.updater = MagicMock(running=False)
        application.running = False
        application.post_init = AsyncMock(side_effect=lambda _: events.append("post_init"))
        application.post_shutdown = AsyncMock(
            side_effect=lambda _: events.append("post_shutdown")
        )
        application.initialize = AsyncMock(side_effect=lambda: events.append("initialize"))
        application.start = AsyncMock(side_effect=lambda: events.append("start"))
        application.shutdown = AsyncMock(side_effect=lambda: events.append("shutdown"))
        application.bot.delete_webhook = AsyncMock(
            side_effect=lambda **_: events.append("delete_webhook")
        )
        async def start_polling(**kwargs):
            events.append("start_polling")
            application.running = True
            application.updater.running = True
            kwargs["error_callback"](Conflict("duplicate polling"))

        async def stop_polling():
            events.append("stop_polling")
            application.updater.running = False

        async def stop_application():
            events.append("app_stop")
            application.running = False

        application.updater.start_polling = AsyncMock(side_effect=start_polling)
        application.updater.stop = AsyncMock(side_effect=stop_polling)
        application.stop = AsyncMock(side_effect=stop_application)
        health = MagicMock()
        health.stop.side_effect = lambda: events.append("health_stop")

        _release_polling_run()
        with self.assertRaises(RuntimeError):
            await run_application(application, health)

        self.assertLess(events.index("delete_webhook"), events.index("start_polling"))
        self.assertLess(events.index("stop_polling"), events.index("app_stop"))
        self.assertIn("post_shutdown", events)
        self.assertIn("shutdown", events)
        self.assertIn("health_stop", events)
        _release_polling_run()

    async def test_post_shutdown_closes_database(self):
        database = MagicMock(spec=Database)
        application = SimpleNamespace(bot_data={"database": database})
        await post_shutdown(application)
        database.close.assert_called_once()


class MenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_donate_routes_to_donation_menu(self):
        context = _context()
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.text = DONATE_STARS_BUTTON
        update = SimpleNamespace(effective_message=message)

        await reply_menu_handler(update, context)

        self.assertEqual(message.reply_text.call_args.args[0], DONATION_MENU_TEXT)

    async def test_reply_video_downloader_routes_to_empty_placeholder(self):
        context = _context()
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.text = VIDEO_DOWNLOADER_BUTTON
        update = SimpleNamespace(effective_message=message)

        await reply_menu_handler(update, context)

        text = message.reply_text.call_args.args[0]
        self.assertIn("🎬 Video Downloader", text)
        self.assertNotIn("http", text.lower())
        self.assertNotIn("quality", text.lower())
        self.assertNotIn("provider", text.lower())
        markup = message.reply_text.call_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "menu:main")


if __name__ == "__main__":
    unittest.main()
