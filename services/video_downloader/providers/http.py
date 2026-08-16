"""Bounded JSON HTTP calls used by optional providers."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

from services.video_downloader.providers.base import ProviderError, ProviderTimeout


MAX_RESPONSE_BYTES = 1_048_576


def _post_json_sync(endpoint: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "NovaBot-VideoDownloader/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError("The provider request failed.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProviderError("The provider response was too large.")
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("The provider returned invalid metadata.") from exc
    if not isinstance(data, dict):
        raise ProviderError("The provider returned an invalid response.")
    return data


async def post_json(
    endpoint: str, payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_post_json_sync, endpoint, payload, timeout),
            timeout=timeout + 1,
        )
    except asyncio.TimeoutError as exc:
        raise ProviderTimeout("The provider request timed out.") from exc