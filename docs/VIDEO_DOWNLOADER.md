# Video Downloader Operations

The downloader is intentionally isolated under `handlers/video_downloader.py`
and `services/video_downloader/`. It requests metadata first, resolves a
temporary provider URL only after a format choice, and never writes media bytes
to Render local storage.

## Provider configuration

- `VIDEO_DOWNLOADER_COBALT_URL` is optional and must point to a deployment-owned
  HTTPS Cobalt endpoint. No public Cobalt instance is assumed.
- `VIDEO_DOWNLOADER_YTDLP_PATH` is optional. If present, yt-dlp is used for
  metadata and format detection only.
- `VIDEO_DOWNLOADER_ALLOW_YTDLP_FALLBACK` must be explicitly enabled before
  yt-dlp direct URLs can be used as a bounded fallback. yt-dlp never receives a
  download command.

Provider response and format contracts are defined in
`services/video_downloader/providers/base.py`; a future provider can implement
that contract and be added to `ProviderRouter` without changing Telegram flow.

## Cloudflare Worker

Delivery requires `VIDEO_DOWNLOADER_WORKER_URL` and
`VIDEO_DOWNLOADER_ACCESS_KEY`. The application encrypts a short-lived payload
with Fernet. The payload contains the temporary upstream URL, request id, and
expiry, so the raw provider URL is not sent to Telegram.

Configure a Cloudflare Worker to:

1. Accept the `token` query parameter from the configured Worker URL.
2. Decrypt and authenticate it using the same access key, without logging it.
3. Reject expired tokens and optionally enforce one-time/request-id replay
   protection.
4. Redirect to the upstream URL with a short cache lifetime, or stream from the
   upstream at the edge.
5. Restrict outbound requests to HTTPS and avoid following untrusted redirects.

The Worker is the access layer, not a permanent media store. Its public URL
must be supplied through `VIDEO_DOWNLOADER_WORKER_URL`; it is never
hard-coded in NovaBot.

## Limits and cleanup

`VIDEO_DOWNLOADER_MAX_MEDIA_BYTES`, concurrency, request timeout, rate limit,
and token TTL are environment-controlled. The bot keeps only metadata and a
pending payment/request tuple in memory. Cleanup removes that state after
delivery, cancellation, payment failure, or an error; no downloader history is
added to SQLite.