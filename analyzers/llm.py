import asyncio
import base64
import json
import time

import anthropic
import cv2
import numpy as np

import config
import monitor

# ── Prompt ────────────────────────────────────────────────────────────────────

_PROMPT = """\
You are a home security AI monitoring one or more cameras.
{camera_context}

Recent activity log (last {window} min, all cameras):
{history}

Analyze the current frame(s) and answer two questions:
1. Is there a person present who is behaving suspiciously?
   (e.g. lurking, attempting to break in, trespassing, acting erratically)
2. Has the situation CHANGED from the recent log?
   Changed = a genuinely new event: new person appearing, new suspicious behaviour, or clear escalation.
   NOT changed = the same ongoing situation that is already recorded above.

Reply with ONLY a JSON object:
{{"suspicious": true/false, "changed": true/false, "reason": "brief explanation"}}
"changed" MUST be false when this is a continuation of an already-logged situation.\
"""


def _camera_context(camera_id: str, has_context: bool) -> str:
    if has_context:
        return (
            f"The FIRST image is from [{camera_id}] which triggered motion detection. "
            "Remaining images are current snapshots from other cameras for additional context."
        )
    return f"The image is from [{camera_id}]."


def _encode(frame: np.ndarray, quality: int) -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.standard_b64encode(buf.tobytes()).decode("utf-8")


# ── Analyzer ──────────────────────────────────────────────────────────────────

class LLMAnalyzer:
    def __init__(self, cooldown_seconds: int = config.LLM_COOLDOWN_SECONDS):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._cooldown = cooldown_seconds
        self._last_call: float = 0
        monitor.stats.llm.model = config.CLAUDE_MODEL
        monitor.stats.llm.cooldown_seconds = cooldown_seconds

    def is_ready(self) -> bool:
        return time.monotonic() - self._last_call >= self._cooldown

    async def analyze(
        self,
        frame: np.ndarray,
        camera_id: str = "",
        context: dict[str, np.ndarray] | None = None,
        history: list[dict] | None = None,
    ) -> dict:
        if not self.is_ready():
            return {"suspicious": False, "changed": False, "reason": "cooldown"}

        self._last_call = time.monotonic()
        monitor.stats.llm.last_call_ts = self._last_call
        monitor.stats.llm.total_calls += 1
        ctx_count = len(context) if context else 0
        monitor.log(
            f"LLM call #{monitor.stats.llm.total_calls} — {camera_id}"
            + (f" + {ctx_count} context cam(s)" if ctx_count else "")
            + f", {len(history or [])} history record(s)",
            "LLM",
        )

        trigger_b64 = _encode(frame, config.JPEG_QUALITY_ANALYSIS)
        context_b64 = {k: _encode(v, config.JPEG_QUALITY_CONTEXT) for k, v in (context or {}).items()}

        import db
        history_text = db.format_history(history or [])
        window_min = config.LLM_HISTORY_WINDOW // 60
        prompt = _PROMPT.format(
            camera_context=_camera_context(camera_id, bool(context_b64)),
            window=window_min,
            history=history_text,
        )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self._call_api, trigger_b64, context_b64, prompt)

        if response.get("suspicious"):
            monitor.stats.llm.suspicious_hits += 1
            monitor.log(
                f"Suspicious ({'changed' if response.get('changed') else 'no change'}): {response.get('reason', '')}",
                "ALERT",
            )
        else:
            monitor.log(f"Not suspicious: {response.get('reason', '')}", "LLM")

        return response

    def _call_api(self, trigger_b64: str, context_b64: dict[str, str], prompt: str) -> dict:
        def img_block(data: str) -> dict:
            return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}

        content: list[dict] = [img_block(trigger_b64)]
        for data in context_b64.values():
            content.append(img_block(data))
        content.append({"type": "text", "text": prompt})

        try:
            message = self._client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=config.CLAUDE_MAX_TOKENS,
                messages=[{"role": "user", "content": content}],
            )
            raw = message.content[0].text.strip()
            result = json.loads(raw)
            result.setdefault("changed", True)  # safe default if model omits it
            return result
        except Exception as e:
            monitor.log(f"LLM error: {e}", "ERROR")
            return {"suspicious": False, "changed": False, "reason": f"error: {e}"}
