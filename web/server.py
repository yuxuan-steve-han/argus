import threading
from typing import TYPE_CHECKING

import cv2
from flask import Flask, Response, render_template_string

import config

if TYPE_CHECKING:
    from cameras.stream import CameraStream

app = Flask(__name__)
_streams: dict[str, "CameraStream"] = {}

_INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Home Security</title>
  <style>
    body { background: #111; color: #eee; font-family: monospace; margin: 0; padding: 16px; }
    h1 { margin-bottom: 16px; }
    .feeds { display: flex; flex-wrap: wrap; gap: 12px; }
    .feed { display: flex; flex-direction: column; align-items: center; }
    .feed span { margin-top: 6px; font-size: 12px; color: #aaa; }
    img { border: 1px solid #333; max-width: 640px; width: 100%; }
  </style>
</head>
<body>
  <h1>Home Security</h1>
  <div class="feeds">
    {% for camera_id in camera_ids %}
    <div class="feed">
      <img src="/feed/{{ camera_id }}" alt="{{ camera_id }}">
      <span>{{ camera_id }}</span>
    </div>
    {% endfor %}
  </div>
</body>
</html>
"""


def register_streams(streams: dict[str, "CameraStream"]):
    _streams.update(streams)


@app.route("/")
def index():
    return render_template_string(_INDEX_HTML, camera_ids=list(_streams.keys()))


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


def start_in_background(port: int):
    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, threaded=True),
        daemon=True,
    )
    thread.start()
    print(f"[web] Serving at http://0.0.0.0:{port}")
