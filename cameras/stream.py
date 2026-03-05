import threading
import time

import cv2
import numpy as np

import monitor


class CameraStream:
    def __init__(self, camera_id: str, url: str):
        self.camera_id = camera_id
        self.url = url
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def _capture_loop(self):
        cam_stats = monitor.stats.camera(self.camera_id)
        cam_stats.status = "connecting"

        cap = cv2.VideoCapture(self.url)
        if not cap.isOpened():
            cam_stats.status = "disconnected"
            monitor.log(f"{self.camera_id}: failed to open stream", "ERROR")
            return

        cam_stats.status = "connected"
        monitor.log(f"{self.camera_id}: stream connected", "CAMERA")

        # FPS tracking
        frame_count = 0
        fps_window_start = time.monotonic()

        while self._running:
            ret, frame = cap.read()
            if not ret:
                cam_stats.status = "disconnected"
                monitor.log(f"{self.camera_id}: stream lost, reconnecting…", "CAMERA")
                cap.release()
                cap = cv2.VideoCapture(self.url)
                if cap.isOpened():
                    cam_stats.status = "connected"
                    monitor.log(f"{self.camera_id}: reconnected", "CAMERA")
                continue

            with self._lock:
                self._frame = frame

            frame_count += 1
            now = time.monotonic()
            elapsed = now - fps_window_start
            if elapsed >= 1.0:
                cam_stats.fps = frame_count / elapsed
                frame_count = 0
                fps_window_start = now

        cap.release()
        cam_stats.status = "disconnected"
