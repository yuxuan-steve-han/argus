import asyncio
import base64
import json
import time

import anthropic
import cv2
import numpy as np

import config
import monitor

PROMPT = (
    "You are a home security camera AI. Analyze this camera frame carefully. "
    "Is there a person present? If so, are they behaving suspiciously "
    "(e.g., lurking, attempting to break in, trespassing, acting erratically)? "
    "Reply with ONLY a JSON object in this exact format: "
    '{"suspicious": true/false, "reason": "brief explanation"}'
)

class LLMAnalyzer:
    def __init__(self, cooldown_seconds: int = config.LLM_COOLDOWN_SECONDS):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._cooldown = cooldown_seconds
        self._last_call: float = 0
        monitor.stats.llm.model = config.CLAUDE_MODEL
        monitor.stats.llm.cooldown_seconds = cooldown_seconds

    def is_ready(self) -> bool:
        return time.monotonic() - self._last_call >= self._cooldown

    async def analyze(self, frame: np.ndarray) -> dict:
        if not self.is_ready():
            return {"suspicious": False, "reason": "cooldown"}

        self._last_call = time.monotonic()
        monitor.stats.llm.last_call_ts = now
        monitor.stats.llm.total_calls += 1
        monitor.log(f"LLM call #{monitor.stats.llm.total_calls} — analyzing frame", "LLM")

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY_ANALYSIS])
        image_data = base64.standard_b64encode(buf.tobytes()).decode("utf-8")

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self._call_api, image_data)

        if response.get("suspicious"):
            monitor.stats.llm.suspicious_hits += 1
            monitor.log(f"Suspicious: {response.get('reason', '')}", "ALERT")
        else:
            monitor.log(f"Not suspicious: {response.get('reason', '')}", "LLM")

        return response

    def _call_api(self, image_data: str) -> dict:
        try:
            message = self._client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=config.CLAUDE_MAX_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_data,
                                },
                            },
                            {"type": "text", "text": PROMPT},
                        ],
                    }
                ],
            )
            raw = message.content[0].text.strip()
            return json.loads(raw)
        except Exception as e:
            monitor.log(f"LLM error: {e}", "ERROR")
            return {"suspicious": False, "reason": f"error: {e}"}
