"""Inline keyboards for CyberBot navigation."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def welcome_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for the welcome screen."""

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Open Main Menu", callback_data="menu:main")]]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu with future options kept visible but inactive."""

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⭐ Donate Stars", callback_data="menu:donate")],
            [
                InlineKeyboardButton(
                    "🎬 Video Downloader",
                    callback_data="future:video",
                )
            ],
            [
                InlineKeyboardButton(
                    "📁 File Tools",
                    callback_data="future:file",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔐 Security Tools",
                    callback_data="future:security",
                )
            ],
            [
                InlineKeyboardButton(
                    "⚙ Settings",
                    callback_data="future:settings",
                )
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu:welcome")],
        ]
    )


def donation_menu_keyboard() -> InlineKeyboardMarkup:
    """Donation amount options."""

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⭐ 10 Stars", callback_data="donate:10")],
            [InlineKeyboardButton("⭐ 15 Stars", callback_data="donate:15")],
            [
                InlineKeyboardButton(
                    "✏ Custom Stars Amount",
                    callback_data="donate:custom",
                )
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
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