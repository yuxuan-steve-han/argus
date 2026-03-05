import asyncio
from datetime import datetime

import config
import db
import monitor
from alerters.discord import DiscordAlerter
from bot import discord_bot
from cameras.stream import CameraStream
from detectors.motion import MotionDetector
from storage import save_frame
from web import server as web_server

if config.LLM_BACKEND == "ollama":
    from analyzers.ollama_local import OllamaAnalyzer as Analyzer
else:
    from analyzers.llm import LLMAnalyzer as Analyzer  # type: ignore[assignment]


import time

import numpy as np

# ── Shared state (asyncio single-threaded — no locks needed) ──────────────────

_latest_frames: dict[str, np.ndarray] = {}
_latest_motion_ts: dict[str, float] = {}

# Cameras that detected motion since the last LLM call: camera_id → (score, frame)
_motion_events: dict[str, tuple[int, np.ndarray]] = {}

# The active debounce task (None, or a running/completed Task)
_debounce_task: asyncio.Task | None = None


def _context_frames(trigger_id: str) -> dict[str, np.ndarray]:
    """Return up to LLM_CONTEXT_CAMERAS snapshots from cameras other than the trigger,
    prioritised by most recent motion."""
    others = {k: v for k, v in _latest_frames.items() if k != trigger_id}
    sorted_keys = sorted(others, key=lambda k: _latest_motion_ts.get(k, 0.0), reverse=True)
    keys = sorted_keys[:config.LLM_CONTEXT_CAMERAS]
    return {k: others[k] for k in keys}


# ── Debounce ──────────────────────────────────────────────────────────────────

def _schedule_debounce(analyzer, alerter) -> None:
    """Start a debounce task if none is already running.  All cameras that detect
    motion within LLM_DEBOUNCE_SECONDS of the first event are included in a single
    LLM call — preventing duplicate queries for the same scene."""
    global _debounce_task
    if _debounce_task is None or _debounce_task.done():
        _debounce_task = asyncio.create_task(_fire_debounced_llm(analyzer, alerter))


async def _fire_debounced_llm(analyzer, alerter) -> None:
    """Wait out the debounce window, then fire ONE LLM call with all cameras
    that registered motion during that window."""
    await asyncio.sleep(config.LLM_DEBOUNCE_SECONDS)

    events = dict(_motion_events)
    _motion_events.clear()
    if not events:
        return

    # Pick trigger = camera with the highest motion score
    trigger_id = max(events, key=lambda k: events[k][0])
    trigger_frame = events[trigger_id][1]

    history = db.get_recent(config.LLM_HISTORY_WINDOW)
    ctx = _context_frames(trigger_id)
    ctx_count = len(ctx)
    monitor.log(
        f"LLM call — trigger: {trigger_id}"
        + (f" + {ctx_count} context cam(s)" if ctx_count else "")
        + f", {len(history)} history record(s)",
        "LLM",
    )

    result = await analyzer.analyze(trigger_frame, trigger_id, ctx, history)

    suspicious = result.get("suspicious", False)
    changed = result.get("changed", True)
    reason = result.get("reason", "unknown")

    db.record(trigger_id, suspicious, changed, reason)

    if suspicious and changed:
        save_frame(trigger_frame, trigger_id)
        monitor.log(f"{trigger_id}: alert sent — {reason}", "ALERT")
        await alerter.send(
            f"⚠️ Security alert [{trigger_id}]: {reason}",
            image=trigger_frame,
            camera_id=trigger_id,
            reason=reason,
        )
    elif suspicious:
        monitor.log(f"{trigger_id}: suspicious but no change — suppressed", "LLM")

    # Motion events that arrived while the LLM call was in-flight would have been
    # blocked from creating a new debounce task (this task wasn't done yet).
    # Kick off a fresh debounce now so they aren't silently dropped.
    if _motion_events:
        _schedule_debounce(analyzer, alerter)


# ── Per-camera loop ───────────────────────────────────────────────────────────

async def monitor_camera(
    stream: CameraStream,
    detector: MotionDetector,
    analyzer,
    alerter: DiscordAlerter,
):
    cam_stats = monitor.stats.camera(stream.camera_id)

    while True:
        frame = stream.get_frame()
        if frame is None:
            await asyncio.sleep(config.MONITOR_LOOP_INTERVAL / 2)
            continue

        _latest_frames[stream.camera_id] = frame

        score, _ = detector.detect(frame)
        cam_stats.motion_score = score

        if score > config.MOTION_THRESHOLD:
            cam_stats.motion_events += 1
            cam_stats.last_motion = datetime.now().strftime("%H:%M:%S")
            _latest_motion_ts[stream.camera_id] = time.monotonic()
            _motion_events[stream.camera_id] = (score, frame)
            _schedule_debounce(analyzer, alerter)

        await asyncio.sleep(config.MONITOR_LOOP_INTERVAL)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    if not config.CAMERA_URLS:
        monitor.log("No CAMERA_URLS configured — add them to .env", "ERROR")
        return

    streams: dict[str, CameraStream] = {}
    for i, url in enumerate(config.CAMERA_URLS):
        camera_id = f"cam{i}"
        stream = CameraStream(camera_id=camera_id, url=url)
        stream.start()
        streams[camera_id] = stream
        monitor.stats.camera(camera_id)  # register in stats immediately
        monitor.log(f"{camera_id}: connecting to {url}", "CAMERA")

    web_url = f"http://localhost:{config.FLASK_PORT}"
    monitor.stats.web_url = web_url
    web_server.register_streams(streams)
    web_server.start_in_background(config.FLASK_PORT)
    monitor.log(f"Web UI started at {web_url}", "INFO")

    db.init(config.DB_PATH)
    monitor.log(f"DB initialised at {config.DB_PATH}", "INFO")

    monitor.stats.llm.model = config.OLLAMA_MODEL if config.LLM_BACKEND == "ollama" else config.CLAUDE_MODEL
    monitor.start()
    monitor.log(f"LLM backend: {config.LLM_BACKEND.upper()} — {monitor.stats.llm.model}", "INFO")

    alerter = DiscordAlerter()
    analyzer = Analyzer()  # shared across all cameras

    tasks = [
        monitor_camera(
            stream=stream,
            detector=MotionDetector(threshold=config.MOTION_THRESHOLD),
            analyzer=analyzer,
            alerter=alerter,
        )
        for stream in streams.values()
    ]

    tasks.append(discord_bot.start())

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
