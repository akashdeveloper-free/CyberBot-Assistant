"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    bot_token: str
    database_path: Path


def load_settings() -> Settings:
    """Load and validate settings without exposing secret values."""

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError(
            "BOT_TOKEN is not configured. Add it as a Replit Secret or environment variable."
        )

    database_path = Path(
        os.getenv("DATABASE_PATH", "database/cyberbot.sqlite3")
    ).expanduser()
    return Settings(bot_token=bot_token, database_path=database_path)