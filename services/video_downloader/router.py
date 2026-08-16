"""Provider priority and failover policy."""

from __future__ import annotations

import logging

from services.video_downloader.config import VideoDownloaderConfig
from services.video_downloader.models import FormatOption, Platform, ResolvedMedia, VideoMetadata
from services.video_downloader.providers.base import ProviderError, ProviderUnavailable, VideoProvider
from services.video_downloader.providers.cobalt import CobaltProvider
from services.video_downloader.providers.ytdlp import YtDlpProvider

logger = logging.getLogger(__name__)


class ProviderRouter:
    """Try configured providers in order without leaking provider details."""

    def __init__(
        self,
        config: VideoDownloaderConfig,
        providers: tuple[VideoProvider, ...] | None = None,
    ) -> None:
        self.config = config
        self.ytdlp = YtDlpProvider(config)
        if providers is not None:
            self.providers = providers
            return
        candidates: list[VideoProvider] = []
        if config.cobalt_url:
            try:
                candidates.append(CobaltProvider(config.cobalt_url, config))
            except ValueError:
                logger.warning("Ignoring an unsafe Cobalt endpoint configuration.")
        if self.ytdlp.configured:
            candidates.append(self.ytdlp)
        self.providers = tuple(candidates)

    async def inspect(self, source_url: str, platform: Platform) -> VideoMetadata:
        if not self.providers:
            raise ProviderUnavailable("No video metadata provider is configured.")
        failures = 0
        for provider in self.providers:
            try:
                return await provider.inspect(source_url, platform)
            except ProviderError:
                failures += 1
                logger.warning("A configured video provider failed; trying the next one.")
        if failures:
            raise ProviderUnavailable("No configured provider could inspect that link.")
        raise ProviderUnavailable("No video metadata provider is configured.")

    async def resolve(
        self, metadata: VideoMetadata, option: FormatOption
    ) -> ResolvedMedia:
        provider = next(
            (candidate for candidate in self.providers if candidate.name == metadata.provider_name),
            None,
        )
        if provider is None:
            raise ProviderUnavailable("The metadata provider is no longer available.")
        try:
            return await provider.resolve(metadata, option)
        except ProviderError:
            if metadata.provider_name != self.ytdlp.name and self.config.allow_ytdlp_fallback and self.ytdlp.configured:
                fallback = await self.ytdlp.inspect(metadata.source_url, Platform.ANY)
                return await self.ytdlp.resolve(fallback, option)
            raise ProviderUnavailable("The selected format is no longer available.")