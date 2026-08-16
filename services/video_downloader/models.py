"""Small immutable data contracts shared by downloader providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Platform(StrEnum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"
    ANY = "any"


class MediaKind(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"


@dataclass(frozen=True)
class DownloadRequest:
    """A validated user request; it never represents downloaded bytes."""

    request_id: str
    user_id: int
    platform: Platform
    source_url: str
    option_id: str

    @property
    def is_4k(self) -> bool:
        return self.option_id in {"4k", "available_4k"}


@dataclass(frozen=True)
class FormatOption:
    """A user-facing option that a provider can resolve later."""

    option_id: str
    label: str
    kind: MediaKind
    is_4k: bool = False
    provider_format_id: str | None = None


@dataclass(frozen=True)
class VideoMetadata:
    """Metadata returned by a provider without downloading media bytes."""

    source_url: str
    title: str
    provider_name: str
    duration_seconds: int | None
    options: tuple[FormatOption, ...]
    provider_data: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ResolvedMedia:
    """A short-lived provider URL that is never sent directly to Telegram."""

    url: str
    provider_name: str
    filename: str
    expires_at: int | None = None
    size_bytes: int | None = None