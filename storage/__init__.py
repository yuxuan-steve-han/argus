import os
from datetime import datetime

import cv2
import numpy as np

import config

_BASE = os.path.join(os.path.dirname(__file__))


def save_frame(frame: np.ndarray, camera_id: str) -> str:
    dir_path = os.path.join(_BASE, camera_id)
    os.makedirs(dir_path, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(dir_path, f"{timestamp}.jpg")
    cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY_STORAGE])
    return path
