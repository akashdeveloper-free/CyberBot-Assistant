# NovaBot — Your Smart Digital Assistant

NovaBot is a modular Telegram bot foundation for an all-in-one digital assistant. It
now includes a metadata-only TikTok/media downloader alongside the secure Telegram
Stars donation flow. Future modules can be added as independent handlers and services
without turning `main.py` into a monolith.

## Current features

- `/start` welcome screen with a persistent Reply Keyboard for NovaBot.
- Inline submenus for File Tools, Security Tools, and Settings.
- Telegram Menu Button commands for `/start`, `/donate`, `/help`, and `/settings`.
- Telegram Stars donation options for 10 Stars, 50 Stars, 100 Stars, and a custom amount.
- Custom amount validation that accepts positive whole numbers only.
- Telegram Stars invoices using `currency="XTR"` and an empty `provider_token`.
- Pre-checkout validation with `PreCheckoutQueryHandler`.
- Successful payment handling with duplicate-charge protection.
- Unified Video Downloader menu for TikTok, YouTube, Facebook, Instagram, and public
  media links.
- yt-dlp handles metadata, thumbnails, normal streams, and explicit HD preparation;
  no RapidAPI key rotation or multi-key quota burning is used.
- Direct normal/HD stream links are exposed through Telegram inline buttons; Render never
  stores or proxies media bytes.
- Five free explicit HD unlocks per user per local day, followed by a one-Star Telegram
  invoice.
- MongoDB Atlas cache with a 36-hour TTL index for normalized metadata and direct URLs.
- Payment safety checks that prepare the HD URL before invoicing and refund when delivery
  cannot be completed after a successful payment.
- Render-compatible `/` and `/health` endpoints running beside Telegram polling.
- Graceful SIGTERM and SIGINT shutdown for the polling updater and application.
- SQLite database preparation for future user accounts and usage metrics.
- Environment-based configuration and structured application logging.

Inactive future menu options are visible for product direction only; File Tools,
Security Tools, and Settings are not activated in this phase.

## Installation

The project targets Python 3.11+ and uses `python-telegram-bot` 22.8.

```bash
python -m venv .venv
. .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

In Replit, install the packages from `requirements.txt` using the project package
manager. Do not commit the generated SQLite database or any local `.env` file.

## Environment setup

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Set `TELEGRAM_BOT_TOKEN` to the token received from BotFather. In Replit or Render,
store it as a Secret; never put the real value in source code, documentation, or Git.
`BOT_TOKEN` remains supported as a backwards-compatible fallback.

Required for the downloader:

- `TELEGRAM_BOT_TOKEN` — Telegram BotFather token.
- `MONGODB_URI` — MongoDB Atlas connection string used for the cache, quota, and paid
  unlock records.
Optional variables:

- `DATABASE_PATH` — SQLite path; defaults to `database/cyberbot.sqlite3`.
- `PORT` — HTTP health server port; Render supplies this automatically.
- `APP_TIMEZONE` — local timezone used for the daily HD reset; defaults to `Asia/Dhaka`.
- `LOG_LEVEL` — logging level; defaults to `INFO`.

## Run

```bash
python main.py
```

The bot uses long polling. Send `/start` in Telegram, use the persistent main
keyboard, and select Donate Stars or `/donate` from Telegram's Menu Button. Telegram
displays the invoice and handles the payment securely. Render uses `render.yaml` and
checks `/health`.

## Project structure

```text
main.py
config/settings.py
handlers/start.py
handlers/commands.py
handlers/menu.py
handlers/donation.py
handlers/video_downloader.py
keyboards/inline_buttons.py
services/health_server.py
services/telegram_stars.py
services/video_downloader.py
database/database.py
utils/logger.py
utils/helpers.py
docs/PROJECT_STATUS.md
```

## Future roadmap

1. User profile and account preferences.
2. File Tools module.
3. Security Utilities module with explicit safety boundaries.
4. AI Assistant features through a managed AI integration.
5. Premium tiers and feature access controls.
6. Admin analytics and expanded donation history.

Each roadmap item should be added as a separate handler/service module and should
reuse the existing settings, logging, database, and navigation layers.