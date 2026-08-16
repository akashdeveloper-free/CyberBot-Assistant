"""Inline keyboards for NovaBot submenus and actions."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def donation_menu_keyboard() -> InlineKeyboardMarkup:
    """Donation amount options."""

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⭐ 10 Stars", callback_data="donate:10")],
            [InlineKeyboardButton("⭐ 50 Stars", callback_data="donate:50")],
            [InlineKeyboardButton("⭐ 100 Stars", callback_data="donate:100")],
            [
                InlineKeyboardButton(
                    "✏ Custom Stars Amount",
                    callback_data="donate:custom",
                )
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
        ]
    )


def donation_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Confirm a selected amount before creating the invoice."""

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Continue Payment",
                    callback_data="donate:continue",
                )
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu:donate")],
        ]
    )


def back_to_donation_keyboard() -> InlineKeyboardMarkup:
    """Back navigation from custom input and invoice preparation screens."""

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Back", callback_data="menu:donate")]]
    )


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Back navigation from inactive future-feature screens."""

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Back", callback_data="menu:main")]]
    )