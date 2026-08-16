"""Process-wide lock preventing duplicate Telegram polling instances."""

from __future__ import annotations

import fcntl
from pathlib import Path
from typing import TextIO


class PollingAlreadyRunningError(RuntimeError):
    """Raised when another local process already owns the polling lock."""


class PollingInstanceLock:
    """Hold an OS file lock for the complete lifetime of the bot process."""

    def __init__(self, path: str | Path = "/tmp/novabot-polling.lock") -> None:
        self.path = Path(path)
        self._handle: TextIO | None = None

    def acquire(self) -> None:
        """Acquire the non-blocking singleton lock or fail closed."""

        if self._handle is not None:
            raise RuntimeError("The NovaBot polling lock is already held by this process.")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise PollingAlreadyRunningError(
                "Another NovaBot process already owns the Telegram polling lock."
            ) from exc

        self._handle = handle

    def release(self) -> None:
        """Release the lock and close its descriptor."""

        handle = self._handle
        self._handle = None
        if handle is None:
            return

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()