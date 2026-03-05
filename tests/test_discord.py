import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from alerters.discord import DiscordAlerter


def make_mock_client(raise_on_post=False):
    """Return (mock_context_manager, mock_client_instance)."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    if raise_on_post:
        resp.raise_for_status.side_effect = Exception("webhook error")

    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, client


# ── Disabled alerter ───────────────────────────────────────────────────────────

class TestDisabledAlerter:
    def test_no_http_call_when_no_webhook(self):
        with patch("alerters.discord.config") as cfg:
            cfg.DISCORD_WEBHOOK_URL = ""
            cfg.DISCORD_TIMEOUT = 15
            cfg.JPEG_QUALITY_ALERT = 85
            alerter = DiscordAlerter()

        with patch("alerters.discord.httpx.AsyncClient") as mock_http:
            asyncio.run(alerter.send("test message"))
            mock_http.assert_not_called()

    def test_still_records_alert_in_stats(self):
        with patch("alerters.discord.config") as cfg:
            cfg.DISCORD_WEBHOOK_URL = ""
            cfg.DISCORD_TIMEOUT = 15
            cfg.JPEG_QUALITY_ALERT = 85
            alerter = DiscordAlerter()

        with patch("alerters.discord.monitor.stats") as mock_stats:
            asyncio.run(alerter.send("test msg", camera_id="cam0", reason="person"))
            mock_stats.record_alert.assert_called_once_with("cam0", "person")


# ── Enabled alerter ────────────────────────────────────────────────────────────

class TestEnabledAlerter:
    def _make_alerter(self):
        with patch("alerters.discord.config") as cfg:
            cfg.DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/test/token"
            cfg.DISCORD_TIMEOUT = 15
            cfg.JPEG_QUALITY_ALERT = 85
            return DiscordAlerter()

    def test_text_only_send(self):
        alerter = self._make_alerter()
        ctx, client = make_mock_client()

        with patch("alerters.discord.httpx.AsyncClient", return_value=ctx):
            asyncio.run(alerter.send("alert message"))

        client.post.assert_called_once()
        call_kwargs = client.post.call_args[1]
        assert call_kwargs["json"]["content"] == "alert message"

    def test_send_with_image(self):
        alerter = self._make_alerter()
        ctx, client = make_mock_client()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        with patch("alerters.discord.httpx.AsyncClient", return_value=ctx):
            asyncio.run(alerter.send("alert", image=frame))

        client.post.assert_called_once()
        call_kwargs = client.post.call_args[1]
        # Image send uses multipart (files + data), not json
        assert "files" in call_kwargs
        assert call_kwargs["data"]["content"] == "alert"

    def test_image_failure_falls_back_to_text(self):
        alerter = self._make_alerter()

        # First post (with image) raises; second post (text-only) succeeds
        resp_ok = MagicMock()
        resp_ok.raise_for_status = MagicMock()
        resp_fail = MagicMock()
        resp_fail.raise_for_status.side_effect = Exception("image upload failed")

        client = AsyncMock()
        client.post = AsyncMock(side_effect=[resp_fail, resp_ok])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with patch("alerters.discord.httpx.AsyncClient", return_value=ctx):
            asyncio.run(alerter.send("alert", image=frame))

        # Should have tried twice: once with image, once text-only fallback
        assert client.post.call_count == 2
        # Second call is the text-only fallback (uses json=)
        second_call_kwargs = client.post.call_args_list[1][1]
        assert "json" in second_call_kwargs

    def test_posts_to_configured_webhook_url(self):
        alerter = self._make_alerter()
        ctx, client = make_mock_client()

        # Config must also be patched during send() since that's when the URL is read
        with patch("alerters.discord.config") as cfg:
            cfg.DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/test/token"
            cfg.DISCORD_TIMEOUT = 15
            cfg.JPEG_QUALITY_ALERT = 85
            with patch("alerters.discord.httpx.AsyncClient", return_value=ctx):
                asyncio.run(alerter.send("msg"))

        url_used = client.post.call_args[0][0]
        assert url_used == "https://discord.com/api/webhooks/test/token"
