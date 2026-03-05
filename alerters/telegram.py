import io

import cv2
import httpx
import numpy as np

import config
import monitor

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


class TelegramAlerter:
    def __init__(self):
        self._enabled = bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)
        if not self._enabled:
            monitor.log("Telegram not configured — alerts will be logged only", "INFO")

    async def send(self, message: str, image: np.ndarray | None = None, camera_id: str = "", reason: str = ""):
        monitor.stats.record_alert(camera_id, reason or message)
        if not self._enabled:
            return
        async with httpx.AsyncClient(timeout=config.TELEGRAM_TIMEOUT) as client:
            if image is not None:
                await self._send_photo(client, message, image)
            else:
                await self._send_message(client, message)

    async def _send_photo(self, client: httpx.AsyncClient, caption: str, image: np.ndarray):
        _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY_ALERT])
        files = {"photo": ("alert.jpg", io.BytesIO(buf.tobytes()), "image/jpeg")}
        data = {"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption}
        try:
            resp = await client.post(f"{TELEGRAM_API}/sendPhoto", data=data, files=files)
            resp.raise_for_status()
        except Exception as e:
            await self._send_message(client, caption)

    async def _send_message(self, client: httpx.AsyncClient, text: str):
        try:
            resp = await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            )
            resp.raise_for_status()
        except Exception as e:
            pass
