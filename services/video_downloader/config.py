"""Environment-backed configuration for the isolated downloader."""

from __future__ import annotations

import os
from dataclasses import dataclass


MIN_LINK_TTL_SECONDS = 60
MAX_LINK_TTL_SECONDS = 900


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a valid number.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a valid integer.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


@dataclass(frozen=True)
class VideoDownloaderConfig:
    """Non-database runtime settings for downloader requests."""

    cobalt_url: str | None = None
    ytdlp_path: str | None = None
    allow_ytdlp_fallback: bool = False
    worker_url: str | None = None
    access_key: str | None = None
    request_timeout_seconds: float = 20.0
    max_media_bytes: int = 50_000_000
    max_concurrent_requests: int = 2
    rate_limit_seconds: float = 3.0
    link_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if (
            not isinstance(self.link_ttl_seconds, int)
            or isinstance(self.link_ttl_seconds, bool)
            or not MIN_LINK_TTL_SECONDS
            <= self.link_ttl_seconds
            <= MAX_LINK_TTL_SECONDS
        ):
            raise ValueError(
                f"link_ttl_seconds must be between "
                f"{MIN_LINK_TTL_SECONDS} and {MAX_LINK_TTL_SECONDS}."
            )

    @classmethod
    def from_environment(cls) -> "VideoDownloaderConfig":
        """Load optional downloader settings without exposing their values."""

        return cls(
            cobalt_url=_optional_env("VIDEO_DOWNLOADER_COBALT_URL"),
            ytdlp_path=_optional_env("VIDEO_DOWNLOADER_YTDLP_PATH"),
            allow_ytdlp_fallback=os.getenv(
                "VIDEO_DOWNLOADER_ALLOW_YTDLP_FALLBACK", ""
            ).strip().lower()
            in {"1", "true", "yes"},
            worker_url=_optional_env("VIDEO_DOWNLOADER_WORKER_URL"),
            access_key=_optional_env("VIDEO_DOWNLOADER_ACCESS_KEY"),
            request_timeout_seconds=_float_env(
                "VIDEO_DOWNLOADER_TIMEOUT_SECONDS", 20.0, 3.0, 60.0
            ),
            max_media_bytes=_int_env(
                "VIDEO_DOWNLOADER_MAX_MEDIA_BYTES", 50_000_000, 1_000_000, 500_000_000
            ),
            max_concurrent_requests=_int_env(
                "VIDEO_DOWNLOADER_MAX_CONCURRENT", 2, 1, 10
            ),
            rate_limit_seconds=_float_env(
                "VIDEO_DOWNLOADER_RATE_LIMIT_SECONDS", 3.0, 0.0, 3600.0
            ),
            link_ttl_seconds=_int_env(
                "VIDEO_DOWNLOADER_LINK_TTL_SECONDS",
                300,
                MIN_LINK_TTL_SECONDS,
                MAX_LINK_TTL_SECONDS,
            ),
        )