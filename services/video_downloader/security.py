"""Validation and sanitization helpers for untrusted downloader input."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    """Raised when a URL is not safe to send to a provider."""


_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}


def _blocked_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not address.is_global


def _validate_static_url(value: str) -> tuple[str, str]:
    if not value or len(value) > 2048:
        raise UnsafeUrlError("That URL is too long or empty.")

    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeUrlError("Only HTTP and HTTPS links are supported.")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Links with embedded credentials are not supported.")
    if not parsed.hostname:
        raise UnsafeUrlError("That link does not contain a valid hostname.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("That link contains an invalid port.") from exc
    if port is not None and port not in {80, 443}:
        raise UnsafeUrlError("Only standard HTTP and HTTPS ports are supported.")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in _BLOCKED_HOSTS or hostname.endswith(
        (".localhost", ".internal", ".local", ".lan")
    ):
        raise UnsafeUrlError("Private network links are not supported.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and _blocked_ip(hostname):
        raise UnsafeUrlError("Private network links are not supported.")
    return value, hostname


def validate_source_url(value: str) -> str:
    """Perform deterministic URL checks before any provider call."""

    return _validate_static_url(value.strip())[0]


def validate_provider_url(value: str) -> str:
    """Require a public HTTPS provider endpoint; never accept arbitrary URLs."""

    url, _ = _validate_static_url(value.strip())
    if urlsplit(url).scheme.lower() != "https":
        raise UnsafeUrlError("Provider endpoints must use HTTPS.")
    return url


def resolve_public_hostname(hostname: str) -> None:
    """Reject DNS names that resolve to loopback or private address space."""

    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(
                hostname,
                443,
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as exc:
        raise UnsafeUrlError("That hostname could not be safely resolved.") from exc
    if not addresses or any(_blocked_ip(address) for address in addresses):
        raise UnsafeUrlError("That link resolves to a private network.")


def sanitize_filename(value: str, fallback: str = "novabot-download") -> str:
    """Keep provider-controlled filenames safe and short for display/use."""

    cleaned = _SAFE_FILENAME.sub("", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = fallback
    return cleaned[:120]