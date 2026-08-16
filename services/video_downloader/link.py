"""Temporary encrypted links for a configured Cloudflare Worker."""

from __future__ import annotations

import json
import time
from urllib.parse import quote, unquote

from cryptography.fernet import Fernet, InvalidToken

from services.video_downloader.config import VideoDownloaderConfig
from services.video_downloader.security import validate_provider_url


class TemporaryLinkError(RuntimeError):
    """Raised when safe link delivery is not configured."""


class TemporaryLinkFactory:
    """Wrap an upstream URL in a short-lived, encrypted Worker token."""

    def __init__(self, config: VideoDownloaderConfig) -> None:
        self.config = config

    def _fernet(self) -> Fernet:
        if not self.config.worker_url or not self.config.access_key:
            raise TemporaryLinkError(
                "Temporary media delivery is not configured."
            )
        try:
            return Fernet(self.config.access_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise TemporaryLinkError("Temporary media delivery is misconfigured.") from exc

    def create(self, upstream_url: str, request_id: str) -> str:
        """Create a Worker URL without putting the raw upstream URL in chat."""

        upstream_url = validate_provider_url(upstream_url)
        expires_at = int(time.time()) + self.config.link_ttl_seconds
        payload = json.dumps(
            {
                "url": upstream_url,
                "request_id": request_id,
                "expires_at": expires_at,
            },
            separators=(",", ":"),
        ).encode()
        token = self._fernet().encrypt(payload).decode("ascii")
        separator = "&" if "?" in self.config.worker_url else "?"
        return f"{self.config.worker_url}{separator}token={quote(token, safe='')}"

    @staticmethod
    def decode_for_worker(token: str, access_key: str) -> dict[str, object]:
        """Test/helper contract for a Worker implementation."""

        try:
            payload = Fernet(access_key.encode("ascii")).decrypt(
                unquote(token).encode("ascii")
            )
            data = json.loads(payload)
        except (InvalidToken, ValueError, TypeError, UnicodeError) as exc:
            raise TemporaryLinkError("Invalid temporary media token.") from exc
        if not isinstance(data, dict) or int(data.get("expires_at", 0)) < int(time.time()):
            raise TemporaryLinkError("The temporary media token has expired.")
        return data