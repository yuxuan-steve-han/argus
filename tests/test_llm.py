import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import numpy as np

from analyzers.llm import LLMAnalyzer, _camera_context, _encode


# ── Pure helpers ───────────────────────────────────────────────────────────────

class TestCameraContext:
    def test_no_context_includes_camera_id(self):
        result = _camera_context("cam0", False)
        assert "cam0" in result

    def test_no_context_does_not_mention_other_cameras(self):
        result = _camera_context("cam0", False)
        assert "other cameras" not in result.lower()

    def test_with_context_labels_trigger_as_first_image(self):
        result = _camera_context("cam2", True)
        assert "cam2" in result
        assert "FIRST" in result

    def test_with_context_mentions_other_cameras(self):
        result = _camera_context("cam2", True)
        assert "other cameras" in result.lower()


class TestEncode:
    def test_returns_string(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        assert isinstance(_encode(frame, 80), str)

    def test_valid_base64(self):
        import base64
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        encoded = _encode(frame, 80)
        decoded = base64.standard_b64decode(encoded)
        # JPEG magic bytes
        assert decoded[:2] == b"\xff\xd8"

    def test_lower_quality_produces_smaller_output(self):
        frame = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        small = _encode(frame, 20)
        large = _encode(frame, 95)
        assert len(small) < len(large)


# ── LLMAnalyzer ────────────────────────────────────────────────────────────────

def make_analyzer() -> LLMAnalyzer:
    with patch("analyzers.llm.anthropic.Anthropic"):
        return LLMAnalyzer()


class TestCallApi:
    def _make_response(self, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.content[0].text = json.dumps(payload)
        return msg

    def test_parses_full_response(self):
        analyzer = make_analyzer()
        analyzer._client.messages.create.return_value = self._make_response(
            {"suspicious": True, "changed": True, "reason": "intruder detected"}
        )
        result = analyzer._call_api("b64", {}, "prompt")
        assert result == {"suspicious": True, "changed": True, "reason": "intruder detected"}

    def test_defaults_changed_true_when_absent(self):
        analyzer = make_analyzer()
        analyzer._client.messages.create.return_value = self._make_response(
            {"suspicious": False, "reason": "all clear"}
        )
        result = analyzer._call_api("b64", {}, "prompt")
        assert result["changed"] is True

    def test_context_images_included_in_api_call(self):
        analyzer = make_analyzer()
        analyzer._client.messages.create.return_value = self._make_response(
            {"suspicious": False, "changed": False, "reason": "clear"}
        )
        context = {"cam1": "ctx_b64_1", "cam2": "ctx_b64_2"}
        analyzer._call_api("trigger_b64", context, "prompt")

        call_kwargs = analyzer._client.messages.create.call_args
        content = call_kwargs[1]["messages"][0]["content"]
        image_blocks = [b for b in content if b.get("type") == "image"]
        # trigger + 2 context = 3 image blocks
        assert len(image_blocks) == 3

    def test_api_error_returns_safe_dict(self):
        analyzer = make_analyzer()
        analyzer._client.messages.create.side_effect = Exception("network error")
        result = analyzer._call_api("b64", {}, "prompt")
        assert result["suspicious"] is False
        assert result["changed"] is False
        assert "error" in result["reason"]

    def test_invalid_json_returns_safe_dict(self):
        analyzer = make_analyzer()
        msg = MagicMock()
        msg.content[0].text = "not valid json"
        analyzer._client.messages.create.return_value = msg
        result = analyzer._call_api("b64", {}, "prompt")
        assert result["suspicious"] is False
        assert result["changed"] is False


class TestAnalyzeAsync:
    def test_updates_last_call_stat(self):
        analyzer = make_analyzer()
        analyzer._client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps({"suspicious": False, "changed": False, "reason": "clear"}))]
        )
        before = time.monotonic()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        asyncio.run(analyzer.analyze(frame, "cam0"))
        import monitor
        assert monitor.stats.llm.last_call_ts >= before

    def test_increments_total_calls(self):
        analyzer = make_analyzer()
        analyzer._client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps({"suspicious": False, "changed": False, "reason": "clear"}))]
        )
        import monitor
        before = monitor.stats.llm.total_calls
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        asyncio.run(analyzer.analyze(frame, "cam0"))
        assert monitor.stats.llm.total_calls == before + 1
