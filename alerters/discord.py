import io

import cv2
import httpx
import numpy as np

import config
import monitor


class DiscordAlerter:
    def __init__(self):
        self._enabled = bool(config.DISCORD_WEBHOOK_URL)
        if not self._enabled:
            monitor.log("Discord webhook not configured — alerts will be logged only", "INFO")

    async def send(self, message: str, image: np.ndarray | None = None, camera_id: str = "", reason: str = ""):
        monitor.stats.record_alert(camera_id, reason or message)
        if not self._enabled:
            return
        async with httpx.AsyncClient(timeout=config.DISCORD_TIMEOUT) as client:
            if image is not None:
                await self._send_with_image(client, message, image)
            else:
                await self._send_message(client, message)

    async def _send_with_image(self, client: httpx.AsyncClient, content: str, image: np.ndarray):
        _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY_ALERT])
        files = {"file": ("alert.jpg", io.BytesIO(buf.tobytes()), "image/jpeg")}
        data = {"content": content}
        try:
            resp = await client.post(config.DISCORD_WEBHOOK_URL, data=data, files=files)
            resp.raise_for_status()
            monitor.log("Discord alert sent (with image)", "ALERT")
        except Exception as e:
            monitor.log(f"Discord webhook (image) failed: {e}", "ERROR")
            await self._send_message(client, content)

    async def _send_message(self, client: httpx.AsyncClient, content: str):
        try:
            resp = await client.post(config.DISCORD_WEBHOOK_URL, json={"content": content})
            resp.raise_for_status()
            monitor.log("Discord alert sent", "ALERT")
        except Exception as e:
            monitor.log(f"Discord webhook failed: {e}", "ERROR")
