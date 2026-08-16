# NovaBot Project Status

**Project:** NovaBot

## Completed features

- Modular Telegram bot foundation with environment-based settings and structured
  logging.
- `/start` welcome flow with a persistent reply-keyboard main menu.
- Telegram command menu for `/start`, `/donate`, `/help`, and `/settings`.
- Main-menu routing for Donate Stars, Help, Settings, and intentionally inactive
  future utilities.
- Telegram Stars donation choices for 10, 50, 100, and custom whole-number
  amounts.
- A shared Stars confirmation screen with `⭐ Pay` and `⬅️ Back`; custom amounts
  use the same screen before an invoice is created.
- Back navigation from every donation input/confirmation/payment-preparation
  screen returns to the Donation menu through `menu:donate`.
- Telegram Stars invoices using `currency="XTR"` and an empty provider token.
- `PreCheckoutQueryHandler` validation for currency, positive amount, payload
  format, and payload/amount matching.
- Successful-payment persistence with duplicate Telegram charge protection.
- SQLite users and donations schema with aggregate Stars and usage counters.
- Render-compatible `/` and `/health` endpoints.
- Guarded single-instance polling, webhook cleanup before polling, conflict
  handling, signal handling, and ordered shutdown cleanup.

## Tested features

The regression suite in `tests/test_regression.py` uses mocked Telegram objects
for user-facing flows and isolated temporary SQLite databases. It covers:

- `/start` and main-menu keyboard registration.
- Donate command and Donation menu options.
- Fixed amount confirmation with `⭐ Pay` and `⬅️ Back`.
- Custom amount validation, confirmation, Pay callback, and Back navigation.
- Invalid Stars values, currency, payload, and amount-mismatch validation.
- Invoice creation callback, successful-payment handling, and duplicate charges.
- Database initialization, user records, donation totals, usage counts, and
  duplicate-charge protection.
- Polling lifecycle guards, webhook deletion, updater/application shutdown,
  health-server cleanup, and health endpoint responses.
- Menu routing and future-feature back navigation.

## Video downloader

- The Video Downloader main-menu entry is implemented as an isolated handler
  and service tree; the other future utility buttons remain unchanged.
- The flow is platform selection → URL validation/SSRF checks → metadata →
  quality/format → processing → temporary Worker link.
- YouTube, TikTok, Facebook, and Any Link option contracts are provider-driven.
  Cobalt is optional and configuration-only; yt-dlp is metadata/format
  detection only unless its bounded direct fallback is explicitly enabled.
- 4K uses the existing XTR Stars settings and a separate downloader payload,
  with `Pay ⭐5` and Back confirmation before delivery.
- No downloader media bytes or history are written to SQLite or Render local
  disk. See `docs/VIDEO_DOWNLOADER.md` for Worker and environment setup.

A real Telegram payment is not charged by the regression suite. Live Telegram
authentication and payment approval require Telegram servers and a user-approved
flow, so they remain deployment verification steps rather than local tests.

## Current architecture

- `main.py` owns application construction, handler registration, polling
  lifecycle, webhook cleanup, signal handling, and ordered shutdown.
- `handlers/` contains thin Telegram update handlers. Donation navigation and
  payment callbacks live in `handlers/donation.py`; general menu routing lives
  in `handlers/menu.py`.
- `keyboards/` is the source of truth for reply and inline button layouts.
- `services/telegram_stars.py` owns Stars invoice construction and pre-checkout
  validation. `services/health_server.py` owns the stoppable HTTP health server.
- `services/polling_lock.py` prevents more than one process from owning polling.
- `database/database.py` owns SQLite schema setup and persistence operations.
- `config/settings.py` loads environment configuration; `.env.example` documents
  names without containing secrets.
- `utils/logger.py` and `utils/helpers.py` hold shared logging and helper logic.

## Protected core components

Future agents must preserve these contracts unless a deliberate, separately
reviewed production change is requested:

- Telegram Stars `XTR` currency, empty provider token, invoice payload format,
  positive amount bounds, pre-checkout validation, and charge-id uniqueness.
- Donation state keys and callback routes, especially `donate:continue` and
  `menu:donate`; every Pay/confirmation screen must retain `⭐ Pay` and
  `⬅️ Back`, with Back returning to the Donation menu.
- SQLite users/donations schema, foreign key relationship, aggregate updates,
  and duplicate-charge behavior.
- Polling single-instance protection, webhook deletion before polling, conflict
  handling, signal registration/removal, updater/application shutdown ordering,
  and health-server stop cleanup.
- Existing NovaBot branding, persistent menu labels, command menu, and inactive
  future-feature behavior.
- Secrets must come only from environment/secret storage. Never place, print,
  commit, or document tokens, passwords, or private credentials.

## Planned features

- User profile and account preferences on top of the existing users table.
- Expanded donation history and admin analytics.
- File Tools and Security Utilities with explicit safety boundaries.
- AI Assistant features through a managed AI integration.
- Premium tiers and feature access controls.

## Future Video Downloader isolation

Video Downloader is planned but is intentionally not implemented in this
recovery. When work begins, isolate it in a dedicated
`handlers/video_downloader.py` and a dedicated
`services/video_downloader/` package, with its own tests and provider-specific
adapters. It must not add download logic to `main.py`, `handlers/donation.py`,
`services/telegram_stars.py`, `database/database.py`, or the polling/health
lifecycle. Route it through the existing menu layer and shared settings/logger
interfaces only after its safety, limits, storage, and provider behavior have
been separately reviewed.

## Source and delivery status

- Source of truth: GitHub `main`.
- This status file describes the state after the current recovery cleanup.
- Do not mark live-payment verification as local PASS without Telegram-side
  approval and evidence.