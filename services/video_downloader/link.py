"""Temporary encrypted links for a configured Cloudflare Worker."""

from __future__ import annotations

import base64
import json
import secrets
import time
from urllib.parse import quote, unquote

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services.video_downloader.config import (
    MAX_LINK_TTL_SECONDS,
    VideoDownloaderConfig,
)
from services.video_downloader.security import validate_provider_url


TOKEN_VERSION = "v1"
AES_GCM_KEY_BYTES = 32
AES_GCM_NONCE_BYTES = 12
AES_GCM_TAG_BYTES = 16


class TemporaryLinkError(RuntimeError):
    """Raised when safe link delivery is not configured."""


class TemporaryLinkFactory:
    """Wrap an upstream URL in a short-lived AES-GCM v1 Worker token.

    The token format is ``v1.<base64url nonce>.<base64url ciphertext+tag>``.
    It uses a 32-byte AES-256-GCM key, a 12-byte nonce, no AAD, and URL-safe
    base64 without padding so Cloudflare Web Crypto can consume it directly.
    """

    def __init__(self, config: VideoDownloaderConfig) -> None:
        self.config = config

    @staticmethod
    def _decode_access_key(access_key: str) -> bytes:
        """Decode the shared AES-256 key used by Python and the Worker."""

        raw = access_key.strip()
        if not raw:
            raise TemporaryLinkError("Temporary media delivery is misconfigured.")

        if len(raw) == AES_GCM_KEY_BYTES:
            return raw.encode("utf-8")

        if len(raw) == AES_GCM_KEY_BYTES * 2:
            try:
                decoded = bytes.fromhex(raw)
            except ValueError:
                decoded = b""
            if len(decoded) == AES_GCM_KEY_BYTES:
                return decoded

        try:
            padded = raw + "=" * (-len(raw) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        except (ValueError, UnicodeError):
            decoded = b""
        if len(decoded) == AES_GCM_KEY_BYTES:
            return decoded

        raise TemporaryLinkError("Temporary media delivery is misconfigured.")

    def _key(self) -> bytes:
        if not self.config.worker_url or not self.config.access_key:
            raise TemporaryLinkError(
                "Temporary media delivery is not configured."
            )
        return self._decode_access_key(self.config.access_key)

    def create(self, upstream_url: str, request_id: str) -> str:
        """Create a Worker URL without putting the raw upstream URL in chat."""

        upstream_url = validate_provider_url(upstream_url)
        expires_at = int(time.time()) + min(
            self.config.link_ttl_seconds, MAX_LINK_TTL_SECONDS
        )
        payload = json.dumps(
            {
                "url": upstream_url,
                "request_id": request_id,
                "expires_at": expires_at,
            },
            separators=(",", ":"),
        ).encode()
        nonce = secrets.token_bytes(AES_GCM_NONCE_BYTES)
        ciphertext = AESGCM(self._key()).encrypt(nonce, payload, None)
        token = ".".join(
            (
                TOKEN_VERSION,
                self._encode_base64url(nonce),
                self._encode_base64url(ciphertext),
            )
        )
        separator = "&" if "?" in self.config.worker_url else "?"
        return f"{self.config.worker_url}{separator}token={quote(token, safe='')}"

    @staticmethod
    def _encode_base64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_base64url(value: str) -> bytes:
        if not value:
            raise ValueError("empty base64url value")
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    @staticmethod
    def decode_for_worker(token: str, access_key: str) -> dict[str, object]:
        """Mirror the Cloudflare Worker AES-GCM v1 decrypt/expiry contract."""

        try:
            parts = unquote(token).split(".")
            if len(parts) != 3 or parts[0] != TOKEN_VERSION:
                raise ValueError("unsupported token version")
            nonce = TemporaryLinkFactory._decode_base64url(parts[1])
            ciphertext = TemporaryLinkFactory._decode_base64url(parts[2])
            if len(nonce) != AES_GCM_NONCE_BYTES or len(ciphertext) <= AES_GCM_TAG_BYTES:
                raise ValueError("invalid AES-GCM envelope")
            key = TemporaryLinkFactory._decode_access_key(access_key)
            payload = AESGCM(key).decrypt(nonce, ciphertext, None)
            data = json.loads(payload.decode("utf-8"))
        except (InvalidTag, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise TemporaryLinkError("Invalid temporary media token.") from exc
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("url"), str)
            or not isinstance(data.get("request_id"), str)
            or not isinstance(data.get("expires_at"), int)
            or isinstance(data.get("expires_at"), bool)
            or data["expires_at"] <= int(time.time())
        ):
            raise TemporaryLinkError("The temporary media token has expired.")
        return data