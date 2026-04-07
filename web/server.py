import os
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

import cv2
from flask import Flask, Response, jsonify, render_template, request

import config
import db
import monitor

if TYPE_CHECKING:
    from cameras.stream import CameraStream

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))
_streams: dict[str, "CameraStream"] = {}


def register_streams(streams: dict[str, "CameraStream"]):
    _streams.update(streams)


@app.route("/")
def index():
    return render_template("index.html", camera_ids=list(_streams.keys()))


@app.route("/feed/<camera_id>")
def feed(camera_id: str):
    if camera_id not in _streams:
        return "Camera not found", 404
    return Response(
        _mjpeg_generator(camera_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


def _mjpeg_generator(camera_id: str):
    stream = _streams[camera_id]
    while True:
        frame = stream.get_frame()
        if frame is None:
            continue
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY_STREAM])
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        )


@app.route("/api/logs")
def api_logs():
    entries = monitor.stats.get_all_log()[-100:]  # last 100 lines
    return jsonify([{"ts": ts, "level": level, "msg": msg} for ts, level, msg in entries])


@app.route("/api/alerts")
def api_alerts():
    limit = request.args.get("limit", 50, type=int)
    alerts = db.get_alerts(min(limit, 200))
    for a in alerts:
        a["time"] = datetime.fromtimestamp(a["ts"]).strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(alerts)


@app.route("/api/status")
def api_status():
    """System status endpoint — also used by Home Assistant REST sensor."""
    s = monitor.stats
    uptime = int(time.monotonic() - s.start_time)
    cameras = {}
    for cam_id, cam in s.cameras.items():
        cameras[cam_id] = {
            "status": cam.status,
            "fps": round(cam.fps, 1),
            "motion_score": cam.motion_score,
            "motion_events": cam.motion_events,
            "last_motion": cam.last_motion,
        }
    return jsonify({
        "uptime_seconds": uptime,
        "cameras": cameras,
        "llm": {
            "model": s.llm.model,
            "total_calls": s.llm.total_calls,
            "suspicious_hits": s.llm.suspicious_hits,
        },
        "alerts": {
            "total_sent": s.alerts.total_sent,
            "recent": [
                {"time": ts, "camera": cam, "reason": reason}
                for ts, cam, reason in s.alerts.log
            ],
        },
    })


def start_in_background(port: int):
    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, threaded=True),
        daemon=True,
    )
    thread.start()
    print(f"[web] Serving at http://0.0.0.0:{port}")
