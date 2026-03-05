import os
import threading
from typing import TYPE_CHECKING

import cv2
from flask import Flask, Response, jsonify, render_template

import config
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


def start_in_background(port: int):
    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, threaded=True),
        daemon=True,
    )
    thread.start()
    print(f"[web] Serving at http://0.0.0.0:{port}")
