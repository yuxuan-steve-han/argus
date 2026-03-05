import cv2
import numpy as np

import config


class MotionDetector:
    def __init__(self, threshold: int):
        self.threshold = threshold
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=config.MOG2_HISTORY,
            varThreshold=config.MOG2_VAR_THRESHOLD,
            detectShadows=False,
        )

    def detect(self, frame: np.ndarray) -> tuple[int, np.ndarray]:
        """
        Returns (motion_score, mask).
        motion_score is the number of changed pixels.
        mask is the foreground binary mask.
        """
        mask = self._subtractor.apply(frame)
        # Remove noise with morphological ops
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        motion_score = int(np.count_nonzero(mask))
        return motion_score, mask
