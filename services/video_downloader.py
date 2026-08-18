"""Metadata-only video extraction, MongoDB caching, and HD quota support.

This module deliberately never asks yt-dlp to download a media file.  It only
extracts short-lived source URLs which Telegram can expose as URL buttons.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

logger = logging.getLogger(__name__)

HD_FREE_LIMIT = 5
HD_PRICE_STARS = 1
CACHE_TTL_HOURS = 36
VIDEO_HD_PAYMENT_PREFIX = "cyberbot:video-hd:"
DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


class VideoDownloaderError(RuntimeError):
    """A safe, user-facing extraction or persistence error."""


class VideoConfigurationError(VideoDownloaderError):
    """The downloader is not configured for this deployment."""


@dataclass(frozen=True)
class VideoMetadata:
    """Small metadata object kept in user context and MongoDB."""

    normalized_url: str
    cache_key: str
    title: str
    thumbnail_url: str | None
    normal_url: str
    hd_url: str
    duration_seconds: int | None = None
    uploader: str | None = None
    photo_urls: tuple[str, ...] = ()


def normalize_url(raw_url: str, *, tiktok_only: bool = False) -> str:
    """Normalize a user URL and drop tracking/query variants.

    Short TikTok hosts are preserved so yt-dlp can resolve them, while all
    query strings and fragments are removed to make cache keys deterministic.
    """

    value = raw_url.strip()
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        raise VideoDownloaderError("Please send a valid http(s) link.")
    if parsed.username or parsed.password:
        raise VideoDownloaderError("Links with embedded credentials are not allowed.")

    if tiktok_only and not is_tiktok_host(host):
        raise VideoDownloaderError("Please send a TikTok link in this menu.")

    # Reject obvious SSRF targets before passing a URL to yt-dlp.
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private or address.is_loopback or address.is_link_local
    ):
        raise VideoDownloaderError("That link cannot be fetched safely.")

    path = parsed.path.rstrip("/") or "/"
    canonical_host = host
    if tiktok_only and host.endswith("tiktok.com") and "/video/" in path:
        canonical_host = "www.tiktok.com"

    return urlunsplit(("https", canonical_host, path, "", ""))


def is_tiktok_host(host: str) -> bool:
    """Return whether a host belongs to TikTok or its short-link domains."""

    return host == "tiktok.com" or host.endswith(".tiktok.com")


def cache_key_for_url(normalized_url: str) -> str:
    """Return a compact, non-sensitive MongoDB cache key."""

    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:32]


def build_video_payment_payload(user_id: int, cache_key: str) -> str:
    """Build a short Stars payload without embedding the original URL."""

    return f"{VIDEO_HD_PAYMENT_PREFIX}{user_id}:{cache_key}"


def parse_video_payment_payload(payload: str) -> tuple[int, str] | None:
    """Parse and validate the user/cache parts of a video payment payload."""

    if not payload.startswith(VIDEO_HD_PAYMENT_PREFIX):
        return None
    parts = payload.removeprefix(VIDEO_HD_PAYMENT_PREFIX).split(":")
    if len(parts) != 2 or len(parts[1]) != 32:
        return None
    try:
        user_id = int(parts[0])
    except ValueError:
        return None
    return user_id, parts[1]


class MongoVideoStore:
    """MongoDB repository for expiring metadata, quota, and payments."""

    def __init__(self, uri: str, database_name: str = "cyberbot_assistant") -> None:
        if not uri.strip():
            raise VideoConfigurationError(
                "MONGODB_URI is not configured; video downloads are unavailable."
            )
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.database = self.client[database_name]
        self.cache = self.database["video_cache"]
        self.usage = self.database["video_hd_usage"]
        self.payments = self.database["video_hd_payments"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes once; the cache and usage collections stay bounded."""

        self.cache.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="video_cache_ttl",
        )
        self.cache.create_index("cache_key", unique=True, name="video_cache_key")
        self.usage.create_index(
            [("user_id", ASCENDING), ("usage_day", ASCENDING)],
            unique=True,
            name="video_usage_user_day",
        )
        self.usage.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="video_usage_ttl",
        )
        self.payments.create_index(
            "telegram_charge_id",
            unique=True,
            name="video_payment_charge",
        )

    def get_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Return a live cache document, guarding against TTL monitor delay."""

        document = self.cache.find_one({"cache_key": cache_key})
        if document is None:
            return None
        expires_at = document.get("expires_at")
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                return None
        return document

    def put_cache(self, metadata: VideoMetadata) -> None:
        """Upsert metadata and direct URLs with a 36-hour TTL."""

        now = datetime.now(timezone.utc)
        self.cache.update_one(
            {"cache_key": metadata.cache_key},
            {
                "$set": {
                    "normalized_url": metadata.normalized_url,
                    "title": metadata.title,
                    "thumbnail_url": metadata.thumbnail_url,
                    "normal_url": metadata.normal_url,
                    "hd_url": metadata.hd_url,
                    "duration_seconds": metadata.duration_seconds,
                    "uploader": metadata.uploader,
                    "photo_urls": list(metadata.photo_urls),
                    "expires_at": now + timedelta(hours=CACHE_TTL_HOURS),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def claim_free_hd(self, user_id: int, username: str | None, usage_day: str) -> bool:
        """Atomically consume one of the five free HD uses for a local day."""

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=3)
        try:
            document = self.usage.find_one_and_update(
                {
                    "user_id": user_id,
                    "usage_day": usage_day,
                    "free_hd_count": {"$lt": HD_FREE_LIMIT},
                },
                {
                    "$inc": {"free_hd_count": 1},
                    "$set": {"username": username, "updated_at": now},
                    "$setOnInsert": {"expires_at": expires_at, "created_at": now},
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # A simultaneous first request may race the unique user/day index.
            document = self.usage.find_one_and_update(
                {
                    "user_id": user_id,
                    "usage_day": usage_day,
                    "free_hd_count": {"$lt": HD_FREE_LIMIT},
                },
                {
                    "$inc": {"free_hd_count": 1},
                    "$set": {"username": username, "updated_at": now},
                },
                return_document=ReturnDocument.AFTER,
            )
        return bool(document and document.get("free_hd_count", HD_FREE_LIMIT + 1) <= HD_FREE_LIMIT)

    def record_payment(
        self,
        user_id: int,
        cache_key: str,
        telegram_charge_id: str,
    ) -> bool:
        """Record a successful paid HD unlock idempotently."""

        try:
            self.payments.insert_one(
                {
                    "user_id": user_id,
                    "cache_key": cache_key,
                    "telegram_charge_id": telegram_charge_id,
                    "created_at": datetime.now(timezone.utc),
                }
            )
        except DuplicateKeyError:
            return False
        return True

    def close(self) -> None:
        """Close the MongoDB client during application shutdown."""

        self.client.close()


def metadata_from_cache(document: dict[str, Any]) -> VideoMetadata:
    """Convert a MongoDB document into the typed metadata object."""

    return VideoMetadata(
        normalized_url=str(document["normalized_url"]),
        cache_key=str(document["cache_key"]),
        title=str(document.get("title") or "Media"),
        thumbnail_url=document.get("thumbnail_url"),
        normal_url=str(document.get("normal_url") or ""),
        hd_url=str(document.get("hd_url") or ""),
        duration_seconds=document.get("duration_seconds"),
        uploader=document.get("uploader"),
        photo_urls=tuple(document.get("photo_urls") or ()),
    )


def _stream_url(info: dict[str, Any], *, hd: bool) -> str | None:
    """Select a direct source URL without merging or downloading formats."""

    formats = [
        item
        for item in info.get("formats", [])
        if item.get("url") and item.get("vcodec") not in (None, "none")
    ]
    if not formats:
        direct_url = info.get("url")
        if not direct_url:
            return None
        if hd and int(info.get("height") or 0) <= 720:
            return None
        return str(direct_url)

    def rank(item: dict[str, Any]) -> tuple[int, float, float]:
        height = int(item.get("height") or 0)
        tbr = float(item.get("tbr") or 0)
        fps = float(item.get("fps") or 0)
        return height, tbr, fps

    if hd:
        # Do not label a 360p/720p-only source as HD.  A paid HD action must
        # always point to a genuinely higher-resolution format.
        hd_formats = [item for item in formats if int(item.get("height") or 0) > 720]
        if not hd_formats:
            return None
        chosen = max(hd_formats, key=rank)
    else:
        sd = [item for item in formats if int(item.get("height") or 0) <= 720]
        chosen = max(sd or formats, key=rank)
    return str(chosen["url"])


def _photo_urls(info: dict[str, Any]) -> tuple[str, ...]:
    """Extract direct image URLs for TikTok photo/slideshow entries."""

    entries = info.get("entries") or []
    photos: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        candidate = entry.get("url")
        if candidate and entry.get("vcodec") in (None, "none"):
            photos.append(str(candidate))
            continue
        for item in entry.get("formats") or []:
            if item.get("url") and item.get("vcodec") in (None, "none"):
                photos.append(str(item["url"]))
                break
    return tuple(dict.fromkeys(photos))


def _metadata_from_info(info: dict[str, Any], normalized_url: str) -> VideoMetadata:
    """Map yt-dlp output to the small, serializable app model."""

    photos = _photo_urls(info)
    normal_url = _stream_url(info, hd=False) or (photos[0] if photos else "")
    hd_url = _stream_url(info, hd=True) or ""
    if not normal_url:
        raise VideoDownloaderError("No direct media stream was available for that link.")

    raw_duration = info.get("duration")
    duration = int(raw_duration) if isinstance(raw_duration, (int, float)) else None
    return VideoMetadata(
        normalized_url=normalized_url,
        cache_key=cache_key_for_url(normalized_url),
        title=str(info.get("title") or "Media"),
        thumbnail_url=info.get("thumbnail"),
        normal_url=normal_url,
        hd_url=hd_url,
        duration_seconds=duration,
        uploader=str(info.get("uploader") or info.get("channel") or "") or None,
        photo_urls=photos,
    )


def _extract_metadata(normalized_url: str) -> VideoMetadata:
    """Run yt-dlp synchronously in a worker thread, metadata only."""

    try:
        import yt_dlp

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": False,
            "extract_flat": False,
            # These headers are used only while resolving the signed CDN URL.
            # The bot never proxies the resulting media bytes.
            "http_headers": {
                **DEFAULT_HTTP_HEADERS,
                "Referer": normalized_url,
            },
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(normalized_url, download=False)
        if not isinstance(info, dict):
            raise VideoDownloaderError("The source returned no usable metadata.")
        return _metadata_from_info(info, normalized_url)
    except VideoDownloaderError:
        raise
    except Exception as exc:
        logger.warning("yt-dlp metadata extraction failed: %s", exc)
        raise VideoDownloaderError(
            "We could not read that media link. It may be private, expired, or unsupported."
        ) from exc


class VideoDownloadService:
    """Application service that combines yt-dlp with the optional Mongo store."""

    def __init__(self, store: MongoVideoStore | None) -> None:
        self.store = store

    async def inspect(self, raw_url: str, *, tiktok_only: bool = False) -> VideoMetadata:
        """Normalize, read cache first, then extract metadata without downloading."""

        normalized = normalize_url(raw_url, tiktok_only=tiktok_only)
        key = cache_key_for_url(normalized)
        if self.store is not None:
            try:
                cached = self.store.get_cache(key)
                if cached is not None:
                    return metadata_from_cache(cached)
            except PyMongoError as exc:
                logger.warning("Could not read video cache; extracting fresh metadata: %s", exc)

        import asyncio

        metadata = await asyncio.to_thread(_extract_metadata, normalized)
        if self.store is not None:
            try:
                self.store.put_cache(metadata)
            except PyMongoError as exc:
                logger.warning("Could not cache video metadata: %s", exc)
        return metadata

    async def prepare_hd(self, metadata: VideoMetadata) -> VideoMetadata:
        """Ensure HD metadata is available before creating a Stars invoice."""

        if metadata.hd_url and metadata.hd_url != metadata.normal_url:
            if self.store is not None:
                try:
                    self.store.put_cache(metadata)
                except PyMongoError as exc:
                    logger.warning("Could not refresh video cache: %s", exc)
            return metadata
        raise VideoDownloaderError("An HD stream is not available for this media.")


def build_store_from_environment(uri: str | None = None) -> MongoVideoStore | None:
    """Create the Mongo store when configured, without breaking legacy startup."""

    configured_uri = (uri if uri is not None else os.getenv("MONGODB_URI", "")).strip()
    if not configured_uri:
        logger.warning("MONGODB_URI is missing; the Video Downloader is disabled.")
        return None
    try:
        return MongoVideoStore(configured_uri)
    except PyMongoError as exc:
        logger.exception("Could not initialize MongoDB video storage: %s", exc)
        return None


def usage_day_key() -> str:
    """Return the current calendar day in the configured midnight timezone."""

    timezone_name = os.getenv("APP_TIMEZONE", "Asia/Dhaka").strip() or "Asia/Dhaka"
    try:
        local_timezone = ZoneInfo(timezone_name)
    except Exception:
        logger.warning("Invalid APP_TIMEZONE=%s; falling back to Asia/Dhaka.", timezone_name)
        local_timezone = ZoneInfo("Asia/Dhaka")
    return datetime.now(local_timezone).date().isoformat()