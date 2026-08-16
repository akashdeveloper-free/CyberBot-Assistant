"""High-level downloader orchestration with bounded, in-memory state."""

from __future__ import annotations

import asyncio
import time
import uuid

from services.video_downloader.config import VideoDownloaderConfig
from services.video_downloader.link import TemporaryLinkError, TemporaryLinkFactory
from services.video_downloader.models import (
    DownloadRequest,
    FormatOption,
    Platform,
    ResolvedMedia,
    VideoMetadata,
)
from services.video_downloader.router import ProviderRouter
from services.video_downloader.providers.base import ProviderError
from services.video_downloader.security import (
    UnsafeUrlError,
    resolve_public_hostname,
    validate_source_url,
)


class DownloadError(RuntimeError):
    """Safe base error for user-facing downloader failures."""


class DownloadConfigurationError(DownloadError):
    """Required provider or delivery configuration is missing."""


class DownloadLinkError(DownloadError):
    """A safe temporary delivery link could not be created."""


class DownloadBusyError(DownloadError):
    """The same user already has an active request."""


class DownloadRateLimitError(DownloadError):
    """The user is requesting downloads too quickly."""


class LargeMediaError(DownloadError):
    """The selected media exceeds the configured safety bound."""


class VideoDownloaderService:
    """No local video bytes are downloaded or persisted by this service."""

    def __init__(
        self,
        config: VideoDownloaderConfig,
        router: ProviderRouter | None = None,
    ) -> None:
        self.config = config
        self.router = router or ProviderRouter(config)
        self.links = TemporaryLinkFactory(config)
        self._semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self._user_locks: dict[int, asyncio.Lock] = {}
        self._last_request_at: dict[int, float] = {}

    @classmethod
    def from_default_environment(cls) -> "VideoDownloaderService":
        return cls(VideoDownloaderConfig.from_environment())

    async def inspect(self, user_id: int, platform: Platform, source_url: str) -> VideoMetadata:
        """Validate a public URL and ask a provider for metadata only."""

        del user_id
        try:
            safe_url = validate_source_url(source_url)
            await asyncio.to_thread(resolve_public_hostname, self._hostname(safe_url))
        except UnsafeUrlError as exc:
            raise DownloadError(str(exc)) from exc
        async with self._semaphore:
            try:
                return await self.router.inspect(safe_url, platform)
            except ProviderError as exc:
                raise DownloadError(
                    "No configured provider could inspect that link."
                ) from exc

    async def prepare_delivery(
        self,
        request: DownloadRequest,
        metadata: VideoMetadata,
        option: FormatOption,
    ) -> str:
        """Resolve one temporary provider URL and wrap it for the Worker."""

        if request.user_id < 1 or option.is_4k != request.is_4k:
            raise DownloadError("That download request is no longer valid.")
        lock = self._user_locks.setdefault(request.user_id, asyncio.Lock())
        if lock.locked():
            raise DownloadBusyError("A download is already being prepared.")
        now = time.monotonic()
        previous = self._last_request_at.get(request.user_id)
        if previous is not None and now - previous < self.config.rate_limit_seconds:
            raise DownloadRateLimitError("Please wait a moment before trying again.")
        self._last_request_at[request.user_id] = now
        try:
            async with lock, self._semaphore:
                try:
                    resolved = await self.router.resolve(metadata, option)
                except ProviderError as exc:
                    raise DownloadError(
                        "The selected format is no longer available."
                    ) from exc
                if (
                    resolved.size_bytes is not None
                    and resolved.size_bytes > self.config.max_media_bytes
                ):
                    raise LargeMediaError("That file is too large for safe link delivery.")
                try:
                    return self.links.create(resolved.url, request.request_id)
                except TemporaryLinkError as exc:
                    raise DownloadLinkError(str(exc)) from exc
        finally:
            self._cleanup_user_lock(request.user_id)

    @staticmethod
    def _hostname(source_url: str) -> str:
        from urllib.parse import urlsplit

        hostname = urlsplit(source_url).hostname
        if not hostname:
            raise DownloadError("That link does not contain a valid hostname.")
        return hostname

    def _cleanup_user_lock(self, user_id: int) -> None:
        lock = self._user_locks.get(user_id)
        if lock is not None and not lock.locked():
            self._user_locks.pop(user_id, None)

    @staticmethod
    def new_request_id() -> str:
        return uuid.uuid4().hex

    def cleanup(self, request_id: str) -> None:
        """Cleanup hook; the service never creates persistent media files."""

        del request_id