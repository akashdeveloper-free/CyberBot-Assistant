"""Provider protocol and safe failure types."""

from __future__ import annotations

from abc import ABC, abstractmethod

from services.video_downloader.models import (
    FormatOption,
    Platform,
    ResolvedMedia,
    VideoMetadata,
)


class ProviderError(RuntimeError):
    """A provider could not inspect or resolve a request."""


class ProviderTimeout(ProviderError):
    """A provider exceeded the configured timeout."""


class ProviderUnavailable(ProviderError):
    """A provider is absent or returned an unavailable response."""


class VideoProvider(ABC):
    """Replaceable provider contract; providers never own Telegram state."""

    name = "provider"

    @abstractmethod
    async def inspect(self, source_url: str, platform: Platform) -> VideoMetadata:
        raise NotImplementedError

    @abstractmethod
    async def resolve(
        self,
        metadata: VideoMetadata,
        option: FormatOption,
    ) -> ResolvedMedia:
        raise NotImplementedError