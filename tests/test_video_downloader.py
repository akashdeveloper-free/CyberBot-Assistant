"""Focused contracts for the isolated video downloader feature."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from handlers.menu import reply_menu_handler
from handlers.video_downloader import (
    PLATFORM_TEXT,
    VIDEO_METADATA_KEY,
    VIDEO_PENDING_KEY,
    VIDEO_PLATFORM_KEY,
    _deliver,
    clear_video_state,
    video_downloader_callback_handler,
    video_downloader_start_handler,
    video_successful_payment_router,
    video_downloader_text_handler,
)
from keyboards.reply_keyboard import VIDEO_DOWNLOADER_BUTTON
from services.video_downloader.config import VideoDownloaderConfig
from services.video_downloader.link import TemporaryLinkFactory
from services.video_downloader.models import (
    DownloadRequest,
    FormatOption,
    MediaKind,
    Platform,
    ResolvedMedia,
    VideoMetadata,
)
from services.video_downloader.payment import (
    VIDEO_4K_STARS,
    build_video_payment_payload,
    validate_video_pre_checkout,
)
from services.video_downloader.providers.base import (
    ProviderError,
    ProviderTimeout,
    VideoProvider,
)
from services.video_downloader.providers.ytdlp import YtDlpProvider
from services.video_downloader.router import ProviderRouter
from services.video_downloader.security import (
    UnsafeUrlError,
    sanitize_filename,
    validate_source_url,
)
from services.video_downloader.service import DownloadLinkError, LargeMediaError, VideoDownloaderService


def _context(service: VideoDownloaderService | None = None):
    return SimpleNamespace(
        user_data={},
        bot=MagicMock(),
        application=SimpleNamespace(
            bot_data={"video_downloader": service} if service else {}
        ),
    )


def _test_key() -> str:
    return base64.urlsafe_b64encode(b"k" * 32).decode("ascii")


def _callback(data: str, chat_id: int = 42):
    message = SimpleNamespace(chat=SimpleNamespace(id=chat_id))
    query = SimpleNamespace(
        data=data,
        message=message,
        from_user=SimpleNamespace(id=chat_id),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    return SimpleNamespace(callback_query=query), query


class FakeProvider(VideoProvider):
    name = "fake"

    def __init__(
        self,
        metadata: VideoMetadata,
        media: ResolvedMedia | None = None,
        failure: Exception | None = None,
    ):
        self.metadata = metadata
        self.media = media
        self.failure = failure
        self.seen_platform: Platform | None = None

    async def inspect(self, source_url: str, platform: Platform) -> VideoMetadata:
        self.seen_platform = platform
        if self.failure:
            raise self.failure
        return self.metadata

    async def resolve(
        self, metadata: VideoMetadata, option: FormatOption
    ) -> ResolvedMedia:
        if self.failure:
            raise self.failure
        if self.media is None:
            raise ProviderError("no fake media")
        return self.media


def _metadata(
    source_url: str = "https://example.com/video",
    option: FormatOption | None = None,
) -> VideoMetadata:
    return VideoMetadata(
        source_url=source_url,
        title="Example video",
        provider_name="fake",
        duration_seconds=12,
        options=(option or FormatOption("1080p", "1080p Video", MediaKind.VIDEO),),
    )


class UrlAndProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_url_validation_and_filename_sanitization(self):
        self.assertEqual(validate_source_url("https://example.com/watch?v=1"), "https://example.com/watch?v=1")
        for unsafe in (
            "file:///etc/passwd",
            "https://127.0.0.1/video",
            "https://localhost/video",
            "https://user:password@example.com/video",
            "https://example.com:8080/video",
        ):
            with self.subTest(unsafe=unsafe), self.assertRaises(UnsafeUrlError):
                validate_source_url(unsafe)
        self.assertEqual(sanitize_filename("../../bad<>name?.mp4"), "badname.mp4")

    def test_supported_tiktok_urls_pass_source_validation(self):
        urls = (
            "https://vt.tiktok.com/ZExample/",
            "https://vm.tiktok.com/ZExample/",
            "https://www.tiktok.com/@user/video/1234567890",
            "https://tiktok.com/@user/video/1234567890",
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(validate_source_url(url), url)

    def test_ytdlp_provider_is_selected_when_binary_is_available(self):
        config = VideoDownloaderConfig()
        with patch(
            "services.video_downloader.providers.ytdlp.shutil.which",
            return_value="/usr/bin/yt-dlp",
        ):
            router = ProviderRouter(config)
        self.assertEqual([provider.name for provider in router.providers], ["yt-dlp"])
        self.assertTrue(router.ytdlp.configured)

    def test_ytdlp_tiktok_metadata_contract(self):
        provider = YtDlpProvider(VideoDownloaderConfig(ytdlp_path="/usr/bin/yt-dlp"))
        metadata = provider._metadata(
            "https://vt.tiktok.com/ZExample/",
            Platform.TIKTOK,
            {
                "title": "TikTok example",
                "duration": 8,
                "formats": [
                    {
                        "url": "https://cdn.example/video.mp4",
                        "vcodec": "h264",
                        "acodec": "aac",
                        "height": 720,
                        "ext": "mp4",
                    }
                ],
            },
        )
        self.assertEqual(metadata.provider_name, "yt-dlp")
        self.assertEqual(metadata.source_url, "https://vt.tiktok.com/ZExample/")
        self.assertEqual(metadata.options[0].option_id, "best")

    async def test_platform_detection_is_carried_to_provider(self):
        provider = FakeProvider(_metadata())
        config = VideoDownloaderConfig(worker_url=None)
        service = VideoDownloaderService(config, ProviderRouter(config, (provider,)))
        with patch("services.video_downloader.service.resolve_public_hostname"):
            result = await service.inspect(
                42, Platform.TIKTOK, "https://example.com/video"
            )
        self.assertEqual(provider.seen_platform, Platform.TIKTOK)
        self.assertEqual(result.provider_name, "fake")

    async def test_provider_timeout_fails_over_to_next_provider(self):
        first = FakeProvider(_metadata(), failure=ProviderTimeout("slow"))
        second = FakeProvider(_metadata())
        router = ProviderRouter(VideoDownloaderConfig(), (first, second))
        result = await router.inspect("https://example.com/video", Platform.YOUTUBE)
        self.assertEqual(result.provider_name, "fake")
        self.assertEqual(second.seen_platform, Platform.YOUTUBE)

    def test_cobalt_is_optional_and_no_random_endpoint_is_created(self):
        with patch(
            "services.video_downloader.providers.ytdlp.shutil.which",
            return_value=None,
        ):
            router = ProviderRouter(VideoDownloaderConfig())
        self.assertNotIn("cobalt", [provider.name for provider in router.providers])


class DownloaderFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_menu_routes_to_downloader(self):
        context = _context()
        message = MagicMock()
        message.text = VIDEO_DOWNLOADER_BUTTON
        message.reply_text = AsyncMock()
        await reply_menu_handler(SimpleNamespace(effective_message=message), context)
        self.assertEqual(message.reply_text.call_args.args[0], PLATFORM_TEXT)

    async def test_platform_and_back_navigation(self):
        context = _context()
        start_message = MagicMock()
        start_message.reply_text = AsyncMock()
        await video_downloader_start_handler(
            SimpleNamespace(effective_message=start_message), context
        )
        update, query = _callback("video:platform:youtube")
        await video_downloader_callback_handler(update, context)
        self.assertEqual(context.user_data[VIDEO_PLATFORM_KEY], "youtube")
        self.assertIn("YouTube", query.edit_message_text.call_args.args[0])

        update, query = _callback("video:platforms")
        await video_downloader_callback_handler(update, context)
        self.assertNotIn(VIDEO_PLATFORM_KEY, context.user_data)
        self.assertEqual(query.edit_message_text.call_args.args[0], PLATFORM_TEXT)

    async def test_all_supported_platform_flows_select_the_requested_platform(self):
        for platform, label in (
            ("youtube", "YouTube"),
            ("tiktok", "TikTok"),
            ("facebook", "Facebook"),
            ("any", "Any Link"),
        ):
            with self.subTest(platform=platform):
                context = _context()
                update, query = _callback(f"video:platform:{platform}")
                await video_downloader_callback_handler(update, context)
                self.assertEqual(context.user_data[VIDEO_PLATFORM_KEY], platform)
                self.assertIn(label, query.edit_message_text.call_args.args[0])

    async def test_url_metadata_routing(self):
        provider = FakeProvider(_metadata())
        config = VideoDownloaderConfig()
        service = VideoDownloaderService(config, ProviderRouter(config, (provider,)))
        context = _context(service)
        context.user_data[VIDEO_PLATFORM_KEY] = Platform.YOUTUBE.value
        message = SimpleNamespace(
            text="https://example.com/video",
            chat=SimpleNamespace(id=42),
            reply_text=AsyncMock(),
        )
        with patch("services.video_downloader.service.resolve_public_hostname"):
            await video_downloader_text_handler(
                SimpleNamespace(effective_message=message), context
            )
        self.assertIsInstance(context.user_data[VIDEO_METADATA_KEY], VideoMetadata)
        self.assertIn("Metadata ready", message.reply_text.call_args.args[0])

    async def test_missing_configuration_is_safe(self):
        option = FormatOption("1080p", "1080p Video", MediaKind.VIDEO)
        provider = FakeProvider(
            _metadata(option=option),
            ResolvedMedia("https://cdn.example/media", "fake", "video.mp4"),
        )
        service = VideoDownloaderService(
            VideoDownloaderConfig(),
            ProviderRouter(VideoDownloaderConfig(), (provider,)),
        )
        request = DownloadRequest("req", 42, Platform.YOUTUBE, "https://example.com/video", "1080p")
        with self.assertRaises(DownloadLinkError):
            await service.prepare_delivery(request, _metadata(option=option), option)

    async def test_large_file_is_rejected_without_delivery(self):
        option = FormatOption("1080p", "1080p Video", MediaKind.VIDEO)
        config = VideoDownloaderConfig(
            worker_url="https://worker.example/access",
            access_key=_test_key(),
            max_media_bytes=100,
        )
        provider = FakeProvider(
            _metadata(option=option),
            ResolvedMedia("https://cdn.example/media", "fake", "video.mp4", size_bytes=101),
        )
        service = VideoDownloaderService(config, ProviderRouter(config, (provider,)))
        request = DownloadRequest("req", 42, Platform.YOUTUBE, "https://example.com/video", "1080p")
        with self.assertRaises(LargeMediaError):
            await service.prepare_delivery(request, _metadata(option=option), option)

    async def test_delivery_uses_one_download_now_button_without_raw_link_message(self):
        option = FormatOption("1080p", "1080p Video", MediaKind.VIDEO)
        config = VideoDownloaderConfig(
            worker_url="https://worker.example/access",
            access_key=_test_key(),
        )
        service = VideoDownloaderService(config)
        service.prepare_delivery = AsyncMock(
            return_value="https://worker.example/access?token=v1.test"
        )
        context = _context(service)
        message = SimpleNamespace(reply_text=AsyncMock())
        request = DownloadRequest(
            "req",
            42,
            Platform.YOUTUBE,
            "https://example.com/video",
            "1080p",
        )

        await _deliver(message, context, request, _metadata(option=option), option)

        message.reply_text.assert_awaited_once()
        text = message.reply_text.call_args.args[0]
        markup = message.reply_text.call_args.kwargs["reply_markup"]
        button = markup.inline_keyboard[0][0]
        self.assertNotIn("v1.test", text)
        self.assertEqual(button.text, "Download Now")
        self.assertEqual(button.url, "https://worker.example/access?token=v1.test")
        self.assertNotIn("VIDEO_DOWNLOADER_PENDING", context.user_data)

    async def test_successful_4k_payment_delivers_download_now_button(self):
        option = FormatOption("4k", "4K Video", MediaKind.VIDEO, is_4k=True)
        config = VideoDownloaderConfig(
            worker_url="https://worker.example/access",
            access_key=_test_key(),
        )
        service = VideoDownloaderService(config)
        service.prepare_delivery = AsyncMock(
            return_value="https://worker.example/access?token=v1.paid"
        )
        context = _context(service)
        request = DownloadRequest(
            "request123",
            42,
            Platform.YOUTUBE,
            "https://example.com/video",
            "4k",
        )
        metadata = _metadata(option=option)
        context.user_data[VIDEO_PENDING_KEY] = (request, metadata, option)
        payload = build_video_payment_payload(42, request.request_id)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=42),
            successful_payment=SimpleNamespace(
                invoice_payload=payload,
                currency="XTR",
                total_amount=VIDEO_4K_STARS,
            ),
            reply_text=AsyncMock(),
        )

        await video_successful_payment_router(
            SimpleNamespace(effective_message=message, effective_user=SimpleNamespace(id=42)),
            context,
        )

        service.prepare_delivery.assert_awaited_once_with(
            request, metadata, option
        )
        markup = message.reply_text.call_args.kwargs["reply_markup"]
        button = markup.inline_keyboard[0][0]
        self.assertEqual(button.text, "Download Now")
        self.assertEqual(button.url, "https://worker.example/access?token=v1.paid")
        self.assertNotIn(VIDEO_PENDING_KEY, context.user_data)

    async def test_cleanup_removes_all_downloader_state(self):
        context = _context()
        context.user_data.update(
            {
                VIDEO_PLATFORM_KEY: "youtube",
                VIDEO_METADATA_KEY: _metadata(),
                VIDEO_PENDING_KEY: ("request",),
            }
        )
        clear_video_state(context)
        self.assertEqual(context.user_data, {})


class PaymentAndLinkTests(unittest.TestCase):
    def test_4k_payment_contract_uses_existing_xtr_amount(self):
        payload = build_video_payment_payload(42, "request123")
        self.assertEqual(VIDEO_4K_STARS, 5)
        self.assertEqual(validate_video_pre_checkout("XTR", 5, payload), (True, None))
        self.assertEqual(
            validate_video_pre_checkout("USD", 5, payload)[0],
            False,
        )
        self.assertEqual(
            validate_video_pre_checkout("XTR", 4, payload)[0],
            False,
        )

    def test_link_is_temporary_encrypted_and_hides_provider_url(self):
        key = _test_key()
        upstream = "https://provider.example/temporary/file.mp4?sig=secret"
        factory = TemporaryLinkFactory(
            VideoDownloaderConfig(
                worker_url="https://worker.example/access",
                access_key=key,
                link_ttl_seconds=300,
            )
        )
        link = factory.create(upstream, "request123")
        self.assertTrue(link.startswith("https://worker.example/access?token="))
        self.assertNotIn(upstream, link)
        token = link.split("token=", 1)[1]
        self.assertEqual(len(token.split(".")), 3)
        self.assertEqual(token.split(".", 1)[0], "v1")
        decoded = factory.decode_for_worker(token, key)
        self.assertEqual(decoded["url"], upstream)
        self.assertEqual(decoded["request_id"], "request123")

    def test_python_token_is_decryptable_by_node_web_crypto_compatible_aes_gcm(self):
        key = _test_key()
        factory = TemporaryLinkFactory(
            VideoDownloaderConfig(
                worker_url="https://worker.example/access",
                access_key=key,
            )
        )
        link = factory.create("https://provider.example/file.mp4", "request123")
        token = link.split("token=", 1)[1]
        expected = factory.decode_for_worker(token, key)
        node_script = r"""
const { webcrypto } = require("node:crypto");
const decode = (value) => Buffer.from(
  value.replace(/-/g, "+").replace(/_/g, "/") +
  "=".repeat((4 - value.length % 4) % 4),
  "base64",
);
(async () => {
  const [keyText, nonceText, ciphertextText] = process.argv.slice(1);
  const key = await webcrypto.subtle.importKey(
    "raw",
    decode(keyText),
    { name: "AES-GCM" },
    false,
    ["decrypt"],
  );
  const plaintext = await webcrypto.subtle.decrypt(
    { name: "AES-GCM", iv: decode(nonceText) },
    key,
    decode(ciphertextText),
  );
  process.stdout.write(Buffer.from(plaintext).toString("utf8"));
})().catch((error) => {
  process.stderr.write(error.message);
  process.exit(1);
});
"""
        version, nonce, ciphertext = token.split(".")
        result = subprocess.run(
            ["node", "-e", node_script, key, nonce, ciphertext],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(version, "v1")
        self.assertEqual(json.loads(result.stdout), expected)

    def test_link_ttl_is_bounded_to_900_seconds(self):
        with self.assertRaises(ValueError):
            VideoDownloaderConfig(link_ttl_seconds=901)
        with self.assertRaises(ValueError):
            VideoDownloaderConfig(link_ttl_seconds=59)

    def test_secret_values_are_not_in_safe_logs_or_filename(self):
        secret_url = "https://provider.example/file?token=do-not-log"
        provider = FakeProvider(_metadata(), failure=ProviderError(secret_url))
        with self.assertLogs("services.video_downloader.router", level=logging.WARNING) as captured:
            router = ProviderRouter(VideoDownloaderConfig(), (provider,))
            with self.assertRaises(ProviderError):
                asyncio.run(router.inspect(secret_url, Platform.ANY))
        self.assertNotIn(secret_url, "\n".join(captured.output))


class ImportTests(unittest.TestCase):
    def test_downloader_modules_compile_and_import(self):
        import handlers.video_downloader
        import services.video_downloader.providers.cobalt
        import services.video_downloader.providers.ytdlp

        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()