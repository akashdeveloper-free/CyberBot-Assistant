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
    """Single clean platform selector for the media downloader."""

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎵 TikTok", callback_data="video:source:tiktok"),
                InlineKeyboardButton("▶️ YouTube", callback_data="video:source:youtube"),
            ],
            [
                InlineKeyboardButton("📘 Facebook", callback_data="video:source:facebook"),
                InlineKeyboardButton("📸 Instagram", callback_data="video:source:instagram"),
            ],
            [InlineKeyboardButton("🔗 Any Public Link", callback_data="video:source:any")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="video:back-main")],
        ]
    )


def video_prompt_keyboard() -> InlineKeyboardMarkup:
    """One consistent back action from a source prompt or result."""

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Downloader", callback_data="video:menu")]]
    )


def media_result_keyboard(metadata: VideoMetadata) -> InlineKeyboardMarkup:
    """Quality choices with direct stream URL buttons."""

    rows = []
    if metadata.hd_url:
        rows.append(
            [
                InlineKeyboardButton(
                    "🌟 Unlock HD / No-Watermark",
                    callback_data="video:hd",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton("📥 Download Normal (Free)", url=metadata.normal_url)]
    )
    for index, photo_url in enumerate(metadata.photo_urls[:8], start=1):
        if index % 2:
            rows.append([])
        rows[-1].append(InlineKeyboardButton(f"🖼 Photo {index}", url=photo_url))
    rows.append([InlineKeyboardButton("⬅️ Downloader", callback_data="video:menu")])
    return InlineKeyboardMarkup(rows)


def media_result_with_hd_link_keyboard(
    metadata: VideoMetadata,
) -> InlineKeyboardMarkup:
    """Show already-authorized direct stream links."""

    rows = [
        [
            InlineKeyboardButton("📥 Download HD Video", url=metadata.hd_url),
            InlineKeyboardButton("📥 Normal (Free)", url=metadata.normal_url),
        ]
    ]
    for index, photo_url in enumerate(metadata.photo_urls[:8], start=1):
        if index % 2:
            rows.append([])
        rows[-1].append(InlineKeyboardButton(f"🖼 Photo {index}", url=photo_url))
    rows.append([InlineKeyboardButton("⬅️ Downloader", callback_data="video:menu")])
    return InlineKeyboardMarkup(rows)