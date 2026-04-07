import io

import cv2
import httpx
import numpy as np

import config
import monitor


class HomeAssistantAlerter:
    """Send security alerts to Home Assistant via its REST API or webhook."""

    def __init__(self):
        self._url = config.HASS_URL
        self._token = config.HASS_TOKEN
        self._webhook_id = config.HASS_WEBHOOK_ID
        self._timeout = config.HASS_TIMEOUT
        self._enabled = bool(self._url and self._token)

        if not self._enabled:
            monitor.log("Home Assistant not configured — HA alerts disabled", "INFO")
        else:
            monitor.log(f"Home Assistant integration enabled ({self._url})", "INFO")

    async def send(self, message: str, image: np.ndarray | None = None,
                   camera_id: str = "", reason: str = ""):
        if not self._enabled:
            return
        headers = {"Authorization": f"Bearer {self._token}"}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # 1. Fire webhook (lightweight trigger for HA automations)
            if self._webhook_id:
                await self._fire_webhook(client, headers, camera_id, reason)

            # 2. Fire an event on the HA event bus for flexible automation
            await self._fire_event(client, headers, message, camera_id, reason)

    async def _fire_webhook(self, client: httpx.AsyncClient, headers: dict,
                            camera_id: str, reason: str):
        url = f"{self._url}/api/webhook/{self._webhook_id}"
        payload = {"camera_id": camera_id, "reason": reason}
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            monitor.log(f"HA webhook fired for {camera_id}", "ALERT")
        except Exception as e:
            monitor.log(f"HA webhook failed: {e}", "ERROR")

    async def _fire_event(self, client: httpx.AsyncClient, headers: dict,
                          message: str, camera_id: str, reason: str):
        url = f"{self._url}/api/events/argus_security_alert"
        payload = {
            "camera_id": camera_id,
            "reason": reason,
            "message": message,
        }
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            monitor.log(f"HA event fired for {camera_id}", "ALERT")
        except Exception as e:
            monitor.log(f"HA event fire failed: {e}", "ERROR")
