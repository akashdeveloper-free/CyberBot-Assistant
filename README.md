# CyberBot — Your Smart Digital Assistant

CyberBot is a modular Telegram bot foundation for an all-in-one digital assistant. The
first production feature is a secure Telegram Stars donation flow. Future modules can
be added as independent handlers and services without turning `main.py` into a
monolith.

## Current features

- `/start` welcome screen for CyberBot.
- Inline main menu for Video Downloader, File Tools, Security Tools, and Settings.
- Telegram Menu Button commands for `/start`, `/donate`, `/help`, and `/settings`.
- Telegram Stars donation options for 10 Stars, 50 Stars, 100 Stars, and a custom amount.
- Custom amount validation that accepts positive whole numbers only.
- Telegram Stars invoices using `currency="XTR"` and an empty `provider_token`.
- Pre-checkout validation with `PreCheckoutQueryHandler`.
- Successful payment handling with duplicate-charge protection.
- Render-compatible `/` and `/health` endpoints running beside Telegram polling.
- Graceful SIGTERM and SIGINT shutdown for the polling updater and application.
- SQLite database preparation for future user accounts and usage metrics.
- Environment-based configuration and structured application logging.

Inactive future menu options are visible for product direction only; Video Downloader,
File Tools, Security Tools, and Settings are not activated in this phase.

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

Set `BOT_TOKEN` to the token received from BotFather. In Replit, store it as a Secret
named `BOT_TOKEN`; never put the real value in source code, documentation, or Git.

Optional variables:

- `DATABASE_PATH` — SQLite path; defaults to `database/cyberbot.sqlite3`.
- `PORT` — HTTP health server port; Render supplies this automatically.
- `LOG_LEVEL` — logging level; defaults to `INFO`.

## Run

```bash
python main.py
```

The bot uses long polling. Send `/start` in Telegram, open the main menu, choose
`/donate` from Telegram's Menu Button, and select a fixed or custom amount. Telegram
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
keyboards/inline_buttons.py
services/health_server.py
services/telegram_stars.py
database/database.py
utils/logger.py
utils/helpers.py
docs/PROJECT_STATUS.md
```

## Future roadmap

1. User profile and account preferences.
2. Video Downloader module with provider-specific services.
3. File Tools module.
4. Security Utilities module with explicit safety boundaries.
5. AI Assistant features through a managed AI integration.
6. Premium tiers and feature access controls.
7. Admin analytics and expanded donation history.

Each roadmap item should be added as a separate handler/service module and should
reuse the existing settings, logging, database, and navigation layers.