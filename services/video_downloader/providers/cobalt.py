"""Optional, configuration-only Cobalt provider.

No public Cobalt instance is assumed. The endpoint must be supplied by the
deployment and can be replaced without changing the downloader handlers.
"""

from __future__ import annotations

from services.video_downloader.config import VideoDownloaderConfig
from services.video_downloader.models import (
    FormatOption,
    MediaKind,
    Platform,
    ResolvedMedia,
    VideoMetadata,
)
from services.video_downloader.providers.base import ProviderError, ProviderUnavailable, VideoProvider
from services.video_downloader.providers.http import post_json
from services.video_downloader.security import sanitize_filename, validate_provider_url


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class CobaltProvider(VideoProvider):
    name = "cobalt"

    def __init__(self, endpoint: str, config: VideoDownloaderConfig) -> None:
        self.endpoint = validate_provider_url(endpoint).rstrip("/")
        self.config = config

    async def _request(
        self, source_url: str, option: FormatOption | None = None
    ) -> dict[str, object]:
        payload: dict[str, object] = {"url": source_url, "downloadMode": "auto"}
        if option is not None:
            if option.kind is MediaKind.AUDIO:
                payload.update({"downloadMode": "audio", "audioFormat": "mp3"})
            elif option.is_4k:
                payload["videoQuality"] = "2160"
            elif option.option_id in {"720p", "1080p", "hd", "sd"}:
                payload["videoQuality"] = option.option_id.replace("p", "")
        result = await post_json(self.endpoint, payload, self.config.request_timeout_seconds)
        status = str(result.get("status", "")).lower()
        if status in {"error", "rate-limit", "redirect", "tunnel", "local"}:
            if status == "error":
                raise ProviderUnavailable("Cobalt could not process that link.")
        return result

    @staticmethod
    def _options(platform: Platform, result: dict[str, object]) -> tuple[FormatOption, ...]:
        raw_qualities = result.get("availableQualities", result.get("qualities", []))
        qualities = {str(value).lower() for value in raw_qualities} if isinstance(raw_qualities, list) else set()
        supports_4k = bool(
            result.get("is4k")
            or result.get("supports4k")
            or {"2160", "2160p", "4k"} & qualities
        )
        if platform is Platform.YOUTUBE:
            options = [
                FormatOption("720p", "720p Video", MediaKind.VIDEO),
                FormatOption("1080p", "1080p Video", MediaKind.VIDEO),
            ]
            if supports_4k:
                options.append(FormatOption("4k", "4K Video ⭐5", MediaKind.VIDEO, True))
            options.append(FormatOption("mp3", "MP3 Audio", MediaKind.AUDIO))
            return tuple(options)
        if platform is Platform.TIKTOK:
            return (
                FormatOption("best", "No-Watermark Video", MediaKind.VIDEO),
                FormatOption("mp3", "MP3 Audio", MediaKind.AUDIO),
            )
        if platform is Platform.FACEBOOK:
            options = [
                FormatOption("hd", "HD Video", MediaKind.VIDEO),
                FormatOption("sd", "SD Video", MediaKind.VIDEO),
            ]
            if supports_4k:
                options.append(FormatOption("4k", "4K Video ⭐5", MediaKind.VIDEO, True))
            options.append(FormatOption("mp3", "MP3 Audio", MediaKind.AUDIO))
            return tuple(options)
        options = [FormatOption("best", "Best Quality", MediaKind.VIDEO)]
        if supports_4k:
            options.append(
                FormatOption("available_4k", "Available 4K Video ⭐5", MediaKind.VIDEO, True)
            )
        options.append(FormatOption("mp3", "MP3 Audio", MediaKind.AUDIO))
        return tuple(options)

    async def inspect(self, source_url: str, platform: Platform) -> VideoMetadata:
        result = await self._request(source_url)
        title = sanitize_filename(
            str(result.get("filename") or result.get("title") or "NovaBot download")
        )
        return VideoMetadata(
            source_url=source_url,
            title=title,
            provider_name=self.name,
            duration_seconds=_as_int(result.get("duration")),
            options=self._options(platform, result),
            provider_data={"initial_response": result},
        )

    async def resolve(
        self, metadata: VideoMetadata, option: FormatOption
    ) -> ResolvedMedia:
        result = await self._request(metadata.source_url, option)
        url = result.get("url")
        if not isinstance(url, str) or not url:
            raise ProviderUnavailable("Cobalt did not return a temporary media URL.")
        return ResolvedMedia(
            url=url,
            provider_name=self.name,
            filename=sanitize_filename(str(result.get("filename") or metadata.title)),
            expires_at=_as_int(result.get("expiresAt") or result.get("expires_at")),
            size_bytes=_as_int(result.get("contentLength") or result.get("size")),
        )