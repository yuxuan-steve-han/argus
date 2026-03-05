import asyncio
from datetime import datetime

import config
import db
import monitor
from alerters.discord import DiscordAlerter
from cameras.stream import CameraStream
from detectors.motion import MotionDetector
from storage import save_frame
from web import server as web_server

if config.LLM_BACKEND == "ollama":
    from analyzers.ollama_local import OllamaAnalyzer as Analyzer
else:
    from analyzers.llm import LLMAnalyzer as Analyzer  # type: ignore[assignment]


import numpy as np

# Shared registry of the latest frame from each camera (asyncio single-threaded, no lock needed)
_latest_frames: dict[str, np.ndarray] = {}


def _context_frames(trigger_id: str) -> dict[str, np.ndarray]:
    """Return up to LLM_CONTEXT_CAMERAS snapshots from cameras other than the trigger."""
    others = {k: v for k, v in _latest_frames.items() if k != trigger_id}
    keys = list(others)[:config.LLM_CONTEXT_CAMERAS]
    return {k: others[k] for k in keys}


async def monitor_camera(
    stream: CameraStream,
    detector: MotionDetector,
    analyzer,
    alerter: DiscordAlerter,
):
    cam_stats = monitor.stats.camera(stream.camera_id)
    pending_frame = None  # latest motion frame captured during cooldown

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
            if analyzer.is_ready():
                monitor.log(f"{stream.camera_id}: motion {score:,} px — sending to LLM", "MOTION")
                pending_frame = None
                history = db.get_recent(config.LLM_HISTORY_WINDOW)
                result = await analyzer.analyze(frame, stream.camera_id, _context_frames(stream.camera_id), history)
            else:
                # Store latest frame so we can analyze it once cooldown lifts
                pending_frame = frame
        elif pending_frame is not None and analyzer.is_ready():
            # Cooldown just expired; motion happened earlier — analyze the saved frame
            monitor.log(f"{stream.camera_id}: analyzing pending motion frame", "MOTION")
            frame_to_analyze = pending_frame
            pending_frame = None
            history = db.get_recent(config.LLM_HISTORY_WINDOW)
            result = await analyzer.analyze(frame_to_analyze, stream.camera_id, _context_frames(stream.camera_id), history)
        else:
            await asyncio.sleep(config.MONITOR_LOOP_INTERVAL)
            continue

        suspicious = result.get("suspicious", False)
        changed = result.get("changed", True)
        reason = result.get("reason", "unknown")

        db.record(stream.camera_id, suspicious, changed, reason)

        if suspicious and changed:
            save_frame(frame, stream.camera_id)
            monitor.log(f"{stream.camera_id}: alert sent — {reason}", "ALERT")
            await alerter.send(
                f"⚠️ Security alert [{stream.camera_id}]: {reason}",
                image=frame,
                camera_id=stream.camera_id,
                reason=reason,
            )
        elif suspicious:
            monitor.log(f"{stream.camera_id}: suspicious but no change — suppressed", "LLM")

        await asyncio.sleep(config.MONITOR_LOOP_INTERVAL)


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

    tasks = [
        monitor_camera(
            stream=stream,
            detector=MotionDetector(threshold=config.MOTION_THRESHOLD),
            analyzer=Analyzer(),
            alerter=alerter,
        )
        for stream in streams.values()
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
