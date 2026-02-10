# ocr-benchmark/backend/app/adapters/paddleocr_adapter.py

import time
from typing import Any, Dict, List

from app.adapters.base import OCRAdapter


class PaddleOCRAdapter(OCRAdapter):
    def __init__(self) -> None:
        self._ocr = None  # lazy init

    @property
    def name(self) -> str:
        return "paddleocr"

    def _get_ocr(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR
            # keep logs minimal + stable
            self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        return self._ocr

    def run(self, file_bytes: bytes, filename: str = "") -> Dict[str, Any]:
        import numpy as np
        import cv2

        t0 = time.time()

        # decode image bytes -> BGR image
        nparr = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Invalid image bytes (cv2.imdecode returned None).")

        ocr = self._get_ocr()

        # PaddleOCR output formats can vary slightly across versions.
        raw = ocr.ocr(img, cls=True)

        # ---- SAFE PARSING (prevents IndexError) ----
        # Typical: raw = [ [ [box, (text, conf)], ... ] ]
        # But if no text: raw = [ [] ] or [] or None
        detections = []
        if raw and isinstance(raw, list):
            if len(raw) == 1 and isinstance(raw[0], list):
                detections = raw[0]  # per-image list
            else:
                detections = raw

        lines: List[Dict[str, Any]] = []
        texts: List[str] = []

        for det in detections:
            # det usually: [box, (text, conf)]
            try:
                box = det[0]
                txt_conf = det[1]
                text = txt_conf[0] if isinstance(txt_conf, (list, tuple)) and len(txt_conf) > 0 else ""
                conf = float(txt_conf[1]) if isinstance(txt_conf, (list, tuple)) and len(txt_conf) > 1 else None
            except Exception:
                # if paddle returns something unexpected, skip that entry instead of crashing
                continue

            if text:
                texts.append(text)
                lines.append({"text": text, "confidence": conf, "box": box})

        latency_ms = int((time.time() - t0) * 1000)

        return {
            "model": self.name,
            "filename": filename,
            "text": "\n".join(texts),   # empty string if nothing detected (NO crash)
            "lines": lines,             # empty list if nothing detected
            "latency_ms": latency_ms,
        }
