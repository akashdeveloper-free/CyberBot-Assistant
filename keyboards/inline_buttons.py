"""Inline keyboards for NovaBot submenus and actions."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services.video_downloader import VideoMetadata


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
                    "⭐ Pay",
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


def media_downloader_keyboard() -> InlineKeyboardMarkup:
    """Main source selector for the media downloader."""

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎵 TikTok", callback_data="video:tiktok"),
                InlineKeyboardButton("🎬 YouTube (Coming)", callback_data="video:coming"),
            ],
            [
                InlineKeyboardButton("📘 Facebook (Coming)", callback_data="video:coming"),
                InlineKeyboardButton("🔗 Any Link", callback_data="video:any"),
            ],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="video:back-main")],
        ]
    )


def tiktok_prompt_keyboard(back_callback: str = "video:menu") -> InlineKeyboardMarkup:
    """Back navigation from a source link prompt."""

    label = (
        "🔙 Back to Video Downloader"
        if back_callback == "video:menu"
        else "🔙 Back to Main Menu"
    )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=back_callback)]]
    )


def media_result_keyboard(metadata: VideoMetadata) -> InlineKeyboardMarkup:
    """Quality choices with direct free URL buttons."""

    rows = [
        [
            InlineKeyboardButton("🌟 HD (No Watermark)", callback_data="video:hd"),
            InlineKeyboardButton("⚡ Normal (Free)", url=metadata.normal_url),
        ]
    ]
    for index, photo_url in enumerate(metadata.photo_urls[:8], start=1):
        rows.append([InlineKeyboardButton(f"🖼 Photo {index}", url=photo_url)])
    rows.append(
        [InlineKeyboardButton("🔙 Back to TikTok Menu", callback_data="video:back-tiktok")]
    )
    return InlineKeyboardMarkup(rows)


def media_result_with_hd_link_keyboard(
    metadata: VideoMetadata,
) -> InlineKeyboardMarkup:
    """Show the already-authorized HD link alongside the free link."""

    rows = [
        [
            InlineKeyboardButton("🌟 HD (No Watermark)", url=metadata.hd_url),
            InlineKeyboardButton("⚡ Normal (Free)", url=metadata.normal_url),
        ]
    ]
    for index, photo_url in enumerate(metadata.photo_urls[:8], start=1):
        rows.append([InlineKeyboardButton(f"🖼 Photo {index}", url=photo_url)])
    rows.append(
        [InlineKeyboardButton("🔙 Back to TikTok Menu", callback_data="video:back-tiktok")]
    )
    return InlineKeyboardMarkup(rows)