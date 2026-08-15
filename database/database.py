"""SQLite persistence prepared for CyberBot's future user system."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Database:
    """Small SQLite repository for users and successful donations."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create the future-ready schema if it does not exist."""

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    join_date TEXT NOT NULL,
                    total_stars INTEGER NOT NULL DEFAULT 0,
                    usage_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS donations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    stars INTEGER NOT NULL CHECK (stars > 0),
                    payload TEXT NOT NULL,
                    telegram_charge_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
                """
            )

    def ensure_user(self, user_id: int, username: str | None) -> None:
        """Create a user record or refresh the current username."""

        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (user_id, username, join_date)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
                """,
                (user_id, username, now),
            )

    def record_usage(self, user_id: int, username: str | None = None) -> None:
        """Increment usage count for future feature analytics."""

        self.ensure_user(user_id, username)
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET usage_count = usage_count + 1 WHERE user_id = ?",
                (user_id,),
            )

    def record_donation(
        self,
        user_id: int,
        username: str | None,
        stars: int,
        payload: str,
        telegram_charge_id: str,
    ) -> bool:
        """Record a donation once and update the user's aggregate total."""

        self.ensure_user(user_id, username)
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO donations
                    (user_id, stars, payload, telegram_charge_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, stars, payload, telegram_charge_id, created_at),
            )
            if cursor.rowcount == 0:
                return False

            connection.execute(
                """
                UPDATE users
                SET total_stars = total_stars + ?, usage_count = usage_count + 1
                WHERE user_id = ?
                """,
                (stars, user_id),
            )
            return True