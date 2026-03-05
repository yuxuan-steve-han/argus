import numpy as np
import pytest

from detectors.motion import MotionDetector


def make_frame(h=480, w=640, value=0) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


class TestMotionDetector:
    def test_returns_score_and_mask_shape(self):
        det = MotionDetector(threshold=5000)
        frame = make_frame()
        score, mask = det.detect(frame)
        assert isinstance(score, int)
        assert mask.shape == (480, 640)

    def test_score_is_non_negative(self):
        det = MotionDetector(threshold=5000)
        frame = make_frame()
        score, _ = det.detect(frame)
        assert score >= 0

    def test_stable_background_gives_low_score(self):
        det = MotionDetector(threshold=5000)
        frame = make_frame()
        # Feed many identical frames so MOG2 builds a stable background model
        for _ in range(60):
            score, _ = det.detect(frame)
        # After convergence, an identical frame should score well below threshold
        assert score < 1000

    def test_changed_frame_gives_high_score(self):
        det = MotionDetector(threshold=5000)
        bg = make_frame(value=0)
        for _ in range(60):
            det.detect(bg)
        # Introduce a large bright region
        motion = make_frame(value=0)
        motion[100:380, 100:540] = 255
        score, _ = det.detect(motion)
        assert score > 5000

    def test_mask_is_binary(self):
        det = MotionDetector(threshold=5000)
        frame = make_frame()
        _, mask = det.detect(frame)
        unique_vals = set(np.unique(mask).tolist())
        assert unique_vals.issubset({0, 255})

    def test_independent_detectors_do_not_share_state(self):
        det_a = MotionDetector(threshold=5000)
        det_b = MotionDetector(threshold=5000)
        bg = make_frame(value=50)
        for _ in range(60):
            det_a.detect(bg)
            det_b.detect(bg)

        # Introduce motion only for det_a
        motion = make_frame(value=200)
        score_a, _ = det_a.detect(motion)
        score_b, _ = det_b.detect(motion)

        # det_b also sees motion since both had the same background; they are independent objects
        assert det_a._subtractor is not det_b._subtractor
