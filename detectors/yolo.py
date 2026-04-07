import cv2
import numpy as np

import config
import monitor


class YOLOFilter:
    """Pre-filter that runs YOLOv8 on a frame and returns detected objects
    matching the configured target classes (e.g. person, car, dog)."""

    def __init__(self):
        from ultralytics import YOLO

        self._model = YOLO(config.YOLO_MODEL)
        self._target_classes = {c.strip().lower() for c in config.YOLO_CLASSES}
        self._confidence = config.YOLO_CONFIDENCE
        monitor.log(
            f"YOLO filter loaded: model={config.YOLO_MODEL}, "
            f"classes={self._target_classes}, conf={self._confidence}",
            "YOLO",
        )

    def detect(self, frame: np.ndarray) -> list[dict]:
        """Run YOLO on *frame*. Returns a list of detections matching the
        target classes, each as ``{class_name, confidence, bbox}``."""
        results = self._model(frame, conf=self._confidence, verbose=False)
        detections: list[dict] = []
        for r in results:
            for box in r.boxes:
                cls_name = r.names[int(box.cls)]
                if cls_name.lower() in self._target_classes:
                    detections.append(
                        {
                            "class_name": cls_name,
                            "confidence": float(box.conf),
                            "bbox": box.xyxy[0].tolist(),
                        }
                    )
        return detections
