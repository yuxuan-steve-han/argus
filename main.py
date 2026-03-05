import asyncio
from datetime import datetime

import config
import monitor
from alerters.telegram import TelegramAlerter
from cameras.stream import CameraStream
from detectors.motion import MotionDetector
from storage import save_frame
from web import server as web_server

if config.LLM_BACKEND == "ollama":
    from analyzers.ollama_local import OllamaAnalyzer as Analyzer
else:
    from analyzers.llm import LLMAnalyzer as Analyzer  # type: ignore[assignment]


async def monitor_camera(
    stream: CameraStream,
    detector: MotionDetector,
    analyzer,
    alerter: TelegramAlerter,
):
    cam_stats = monitor.stats.camera(stream.camera_id)
    while True:
        frame = stream.get_frame()
        if frame is None:
            await asyncio.sleep(config.MONITOR_LOOP_INTERVAL / 2)
            continue

        score, _ = detector.detect(frame)
        cam_stats.motion_score = score

        if score > config.MOTION_THRESHOLD:
            cam_stats.motion_events += 1
            cam_stats.last_motion = datetime.now().strftime("%H:%M:%S")
            monitor.log(f"{stream.camera_id}: motion {score:,} px — sending to LLM", "MOTION")

            result = await analyzer.analyze(frame)

            if result.get("suspicious"):
                reason = result.get("reason", "unknown")
                save_frame(frame, stream.camera_id)
                monitor.log(f"{stream.camera_id}: alert sent — {reason}", "ALERT")
                await alerter.send(
                    f"⚠️ Security alert [{stream.camera_id}]: {reason}",
                    image=frame,
                    camera_id=stream.camera_id,
                    reason=reason,
                )

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

    monitor.stats.llm.model = config.OLLAMA_MODEL if config.LLM_BACKEND == "ollama" else config.CLAUDE_MODEL
    monitor.start()
    monitor.log(f"LLM backend: {config.LLM_BACKEND.upper()} — {monitor.stats.llm.model}", "INFO")

    alerter = TelegramAlerter()

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
