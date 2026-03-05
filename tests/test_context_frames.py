"""
Tests for _context_frames() in main.py — verifies camera selection and
motion-recency prioritisation without starting the full system.
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

# Inject stubs for the analyzer modules before importing main, so we don't need
# a real Anthropic API key or Ollama server.  We manually manage only the keys
# we care about — using patch.dict would restore ALL newly-added sys.modules
# entries on exit (including cv2 and its submodules), breaking later test files.
import sys

_MOCK_KEYS = ["analyzers.llm", "analyzers.ollama_local", "anthropic"]
_fake_analyzer_module = MagicMock()
_saved_modules = {k: sys.modules.get(k) for k in _MOCK_KEYS}

sys.modules["analyzers.llm"] = _fake_analyzer_module
sys.modules["analyzers.ollama_local"] = _fake_analyzer_module
sys.modules["anthropic"] = MagicMock()

import main as _main  # noqa: E402  (intentionally after sys.modules patch)

# Restore the original values for the mocked keys so other test files that
# directly import analyzers.llm (e.g. test_llm.py) get the real module.
for _k, _v in _saved_modules.items():
    if _v is None:
        sys.modules.pop(_k, None)
    else:
        sys.modules[_k] = _v


def _make_frame() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


def setup_function():
    """Reset shared state before each test."""
    _main._latest_frames.clear()
    _main._latest_motion_ts.clear()
    _main._motion_events.clear()
    _main._debounce_task = None


# ── Basic selection ────────────────────────────────────────────────────────────

def test_excludes_trigger_camera():
    _main._latest_frames["cam0"] = _make_frame()
    _main._latest_frames["cam1"] = _make_frame()
    result = _main._context_frames("cam0")
    assert "cam0" not in result
    assert "cam1" in result


def test_returns_empty_when_only_trigger_camera():
    _main._latest_frames["cam0"] = _make_frame()
    result = _main._context_frames("cam0")
    assert result == {}


def test_returns_empty_when_no_cameras():
    result = _main._context_frames("cam0")
    assert result == {}


def test_respects_llm_context_cameras_limit():
    for i in range(6):
        _main._latest_frames[f"cam{i}"] = _make_frame()
        _main._latest_motion_ts[f"cam{i}"] = time.monotonic()

    with patch("main.config") as mock_cfg:
        mock_cfg.LLM_CONTEXT_CAMERAS = 3
        result = _main._context_frames("cam0")

    assert len(result) == 3
    assert "cam0" not in result


# ── Motion-recency prioritisation ─────────────────────────────────────────────

def test_cameras_sorted_by_most_recent_motion():
    for i in range(4):
        _main._latest_frames[f"cam{i}"] = _make_frame()

    now = time.monotonic()
    _main._latest_motion_ts["cam1"] = now - 10   # most recent
    _main._latest_motion_ts["cam2"] = now - 30
    _main._latest_motion_ts["cam3"] = now - 60   # least recent
    # cam0 is trigger; cam1/2/3 are candidates

    with patch("main.config") as mock_cfg:
        mock_cfg.LLM_CONTEXT_CAMERAS = 2
        result = _main._context_frames("cam0")

    # Should pick the 2 with most recent motion: cam1 and cam2
    assert set(result.keys()) == {"cam1", "cam2"}


def test_cameras_with_no_motion_sort_last():
    for i in range(4):
        _main._latest_frames[f"cam{i}"] = _make_frame()

    now = time.monotonic()
    _main._latest_motion_ts["cam1"] = now - 5    # has motion
    # cam2, cam3 have never triggered motion (not in _latest_motion_ts)

    with patch("main.config") as mock_cfg:
        mock_cfg.LLM_CONTEXT_CAMERAS = 1
        result = _main._context_frames("cam0")

    # cam1 has the most recent motion; should be selected first
    assert set(result.keys()) == {"cam1"}


def test_all_cameras_without_motion_still_returns_up_to_limit():
    for i in range(3):
        _main._latest_frames[f"cam{i}"] = _make_frame()
    # No entries in _latest_motion_ts

    with patch("main.config") as mock_cfg:
        mock_cfg.LLM_CONTEXT_CAMERAS = 2
        result = _main._context_frames("cam0")

    assert len(result) == 2
    assert "cam0" not in result


def test_frames_in_result_are_original_arrays():
    frame_a = np.full((10, 10, 3), 42, dtype=np.uint8)
    _main._latest_frames["cam0"] = _make_frame()
    _main._latest_frames["cam1"] = frame_a

    with patch("main.config") as mock_cfg:
        mock_cfg.LLM_CONTEXT_CAMERAS = 3
        result = _main._context_frames("cam0")

    assert result["cam1"] is frame_a


# ── Debounce ───────────────────────────────────────────────────────────────────

def test_schedule_debounce_creates_task():
    fake_analyzer = MagicMock()
    fake_alerter = MagicMock()

    async def _run():
        _main._schedule_debounce(fake_analyzer, fake_alerter)
        assert _main._debounce_task is not None
        assert not _main._debounce_task.done()
        _main._debounce_task.cancel()

    asyncio.run(_run())


def test_schedule_debounce_only_one_task_per_window():
    fake_analyzer = MagicMock()
    fake_alerter = MagicMock()

    async def _run():
        _main._schedule_debounce(fake_analyzer, fake_alerter)
        task_a = _main._debounce_task
        _main._schedule_debounce(fake_analyzer, fake_alerter)
        task_b = _main._debounce_task
        assert task_a is task_b  # second call reuses the same task
        task_a.cancel()

    asyncio.run(_run())


def test_debounce_picks_highest_motion_as_trigger():
    """_fire_debounced_llm should pick the camera with the highest score as trigger."""
    calls = []

    async def fake_analyze(frame, camera_id="", context=None, history=None):
        calls.append(camera_id)
        return {"suspicious": False, "changed": False, "reason": "clear"}

    fake_analyzer = MagicMock()
    fake_analyzer.analyze = fake_analyze
    fake_alerter = MagicMock()
    fake_alerter.send = AsyncMock()

    frame_lo = np.full((10, 10, 3), 1, dtype=np.uint8)
    frame_hi = np.full((10, 10, 3), 2, dtype=np.uint8)

    _main._motion_events["cam0"] = (1000, frame_lo)   # low score
    _main._motion_events["cam1"] = (9000, frame_hi)   # high score → should be trigger

    async def _run():
        with patch("main.db") as mock_db, patch("main.config") as cfg:
            mock_db.get_recent.return_value = []
            mock_db.record = MagicMock()
            cfg.LLM_DEBOUNCE_SECONDS = 0.0
            cfg.LLM_HISTORY_WINDOW = 300
            cfg.LLM_CONTEXT_CAMERAS = 3
            await _main._fire_debounced_llm(fake_analyzer, fake_alerter)

    asyncio.run(_run())
    assert calls == ["cam1"]


def test_debounce_clears_motion_events_after_firing():
    fake_analyzer = MagicMock()
    fake_analyzer.analyze = AsyncMock(
        return_value={"suspicious": False, "changed": False, "reason": "clear"}
    )
    fake_alerter = MagicMock()
    fake_alerter.send = AsyncMock()

    _main._motion_events["cam0"] = (5000, _make_frame())

    async def _run():
        with patch("main.db") as mock_db, patch("main.config") as cfg:
            mock_db.get_recent.return_value = []
            mock_db.record = MagicMock()
            cfg.LLM_DEBOUNCE_SECONDS = 0.0
            cfg.LLM_HISTORY_WINDOW = 300
            cfg.LLM_CONTEXT_CAMERAS = 3
            await _main._fire_debounced_llm(fake_analyzer, fake_alerter)

    asyncio.run(_run())
    assert _main._motion_events == {}


def test_motion_during_llm_call_triggers_followup_debounce():
    """Events that arrive while the LLM is in flight must not be silently dropped.
    After the call completes, _fire_debounced_llm should schedule a new debounce."""
    call_count = 0

    async def fake_analyze(frame, camera_id="", context=None, history=None):
        nonlocal call_count
        call_count += 1
        # Simulate motion arriving on cam1 while cam0's LLM call is in flight
        if call_count == 1:
            _main._motion_events["cam1"] = (8000, _make_frame())
        return {"suspicious": False, "changed": False, "reason": "clear"}

    fake_analyzer = MagicMock()
    fake_analyzer.analyze = fake_analyze
    fake_alerter = MagicMock()
    fake_alerter.send = AsyncMock()

    _main._motion_events["cam0"] = (5000, _make_frame())

    async def _run():
        with patch("main.db") as mock_db, patch("main.config") as cfg:
            mock_db.get_recent.return_value = []
            mock_db.record = MagicMock()
            cfg.LLM_DEBOUNCE_SECONDS = 0.0
            cfg.LLM_HISTORY_WINDOW = 300
            cfg.LLM_CONTEXT_CAMERAS = 3
            # First call
            await _main._fire_debounced_llm(fake_analyzer, fake_alerter)
            # The follow-up debounce task should now exist and be running
            assert _main._debounce_task is not None
            assert not _main._debounce_task.done()
            # Let the follow-up task complete
            await _main._debounce_task

    asyncio.run(_run())
    assert call_count == 2  # second call processed cam1's event
