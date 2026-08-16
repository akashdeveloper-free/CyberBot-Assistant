"""Metadata-only yt-dlp provider and explicitly bounded direct fallback."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from services.video_downloader.config import VideoDownloaderConfig
from services.video_downloader.models import (
    FormatOption,
    MediaKind,
    Platform,
    ResolvedMedia,
    VideoMetadata,
)
from services.video_downloader.providers.base import ProviderError, ProviderUnavailable, VideoProvider
from services.video_downloader.security import sanitize_filename


class YtDlpProvider(VideoProvider):
    name = "yt-dlp"

    def __init__(self, config: VideoDownloaderConfig) -> None:
        self.config = config
        self.binary = config.ytdlp_path or shutil.which("yt-dlp")

    @property
    def configured(self) -> bool:
        return bool(self.binary)

    async def inspect(self, source_url: str, platform: Platform) -> VideoMetadata:
        if not self.binary:
            raise ProviderUnavailable("yt-dlp is not configured.")
        command = [
            str(Path(self.binary)),
            "--dump-single-json",
            "--skip-download",
            "--no-playlist",
            "--no-warnings",
            "--socket-timeout",
            str(int(self.config.request_timeout_seconds)),
            source_url,
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=self.config.request_timeout_seconds + 1
            )
        except asyncio.TimeoutError as exc:
            if "process" in locals():
                process.kill()
                await process.wait()
            raise ProviderError("yt-dlp metadata lookup timed out.") from exc
        except OSError as exc:
            raise ProviderUnavailable("yt-dlp could not be started.") from exc
        if process.returncode != 0 or len(stdout) > 1_048_576:
            raise ProviderError("yt-dlp could not inspect that link.")
        try:
            result = json.loads(stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("yt-dlp returned invalid metadata.") from exc
        if not isinstance(result, dict):
            raise ProviderError("yt-dlp returned invalid metadata.")
        return self._metadata(source_url, platform, result)

    def _metadata(
        self, source_url: str, platform: Platform, result: dict[str, Any]
    ) -> VideoMetadata:
        formats = result.get("formats")
        safe_formats = [item for item in formats if isinstance(item, dict)] if isinstance(formats, list) else []
        video_formats = [
            item
            for item in safe_formats
            if item.get("url")
            and item.get("vcodec") not in {None, "none"}
            and item.get("acodec") not in {None, "none"}
        ]
        audio_formats = [
            item
            for item in safe_formats
            if item.get("url")
            and item.get("vcodec") in {None, "none"}
            and item.get("acodec") not in {None, "none"}
            and str(item.get("ext", "")).lower() == "mp3"
        ]
        has_4k = any(int(item.get("height") or 0) >= 2160 for item in video_formats)
        if platform is Platform.YOUTUBE:
            options = [
                FormatOption("720p", "720p Video", MediaKind.VIDEO),
                FormatOption("1080p", "1080p Video", MediaKind.VIDEO),
            ]
            if has_4k:
                options.append(FormatOption("4k", "4K Video ⭐5", MediaKind.VIDEO, True))
            if audio_formats:
                options.append(FormatOption("mp3", "MP3 Audio", MediaKind.AUDIO))
        elif platform is Platform.TIKTOK:
            options = [FormatOption("best", "No-Watermark Video", MediaKind.VIDEO)]
            if audio_formats:
                options.append(FormatOption("mp3", "MP3 Audio", MediaKind.AUDIO))
        elif platform is Platform.FACEBOOK:
            options = [
                FormatOption("hd", "HD Video", MediaKind.VIDEO),
                FormatOption("sd", "SD Video", MediaKind.VIDEO),
            ]
            if has_4k:
                options.append(FormatOption("4k", "4K Video ⭐5", MediaKind.VIDEO, True))
            if audio_formats:
                options.append(FormatOption("mp3", "MP3 Audio", MediaKind.AUDIO))
        else:
            options = [FormatOption("best", "Best Quality", MediaKind.VIDEO)]
            if has_4k:
                options.append(
                    FormatOption("available_4k", "Available 4K Video ⭐5", MediaKind.VIDEO, True)
                )
            if audio_formats:
                options.append(FormatOption("mp3", "MP3 Audio", MediaKind.AUDIO))
        return VideoMetadata(
            source_url=source_url,
            title=sanitize_filename(str(result.get("title") or "NovaBot download")),
            provider_name=self.name,
            duration_seconds=int(result["duration"]) if result.get("duration") else None,
            options=tuple(options),
            provider_data={"formats": safe_formats},
        )

    async def resolve(
        self, metadata: VideoMetadata, option: FormatOption
    ) -> ResolvedMedia:
        if not self.config.allow_ytdlp_fallback:
            raise ProviderUnavailable("yt-dlp direct fallback is disabled.")
        candidates = metadata.provider_data.get("formats", [])
        if not isinstance(candidates, list):
            raise ProviderUnavailable("yt-dlp metadata has no usable formats.")

        def height(item: dict[str, Any]) -> int:
            try:
                return int(item.get("height") or 0)
            except (TypeError, ValueError):
                return 0

        matching = [
            item
            for item in candidates
            if isinstance(item.get("url"), str)
            and item.get("vcodec") not in {None, "none"}
            and item.get("acodec") not in {None, "none"}
            and (
                option.kind is MediaKind.VIDEO
                or (
                    option.kind is MediaKind.AUDIO
                    and str(item.get("ext", "")).lower() == "mp3"
                )
            )
        ]
        if option.is_4k:
            matching = [item for item in matching if height(item) >= 2160]
        elif option.option_id == "1080p":
            matching = [item for item in matching if height(item) <= 1080]
        elif option.option_id == "720p":
            matching = [item for item in matching if height(item) <= 720]
        if not matching:
            raise ProviderUnavailable("yt-dlp has no safe format for that choice.")
        chosen = max(matching, key=height)
        size = chosen.get("filesize") or chosen.get("filesize_approx")
        try:
            size_bytes = int(size) if size is not None else None
        except (TypeError, ValueError):
            size_bytes = None
        if size_bytes is not None and size_bytes > self.config.max_media_bytes:
            raise ProviderUnavailable("The selected media is too large.")
        return ResolvedMedia(
            url=str(chosen["url"]),
            provider_name=self.name,
            filename=sanitize_filename(str(metadata.title)),
            size_bytes=size_bytes,
        )