# ocr-benchmark/backend/app/adapters/paddleocr_adapter.py

import time
import io
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from app.adapters.base import OCRAdapter


class PaddleOCRAdapter(OCRAdapter):
    def __init__(self):
        # Lazy init (first request will load models)
        self._ocr = None

    @property
    def name(self) -> str:
        return "paddleocr"

    def _get_ocr(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR
            # show_log=False -> removes huge config spam
            self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        return self._ocr

    def run(
        self,
        image_bytes: Optional[bytes] = None,
        filename: str = "",
        mime_type: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        if image_bytes is None:
            # accept alternative keys if main passes differently
            for k in ("file_bytes", "bytes", "image", "content", "data"):
                if k in kwargs and kwargs[k] is not None:
                    image_bytes = kwargs[k]
                    break
        if image_bytes is None:
            raise RuntimeError("PaddleOCRAdapter.run() did not receive image bytes")

        t0 = time.time()

        # bytes -> PIL -> numpy
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)[:, :, ::-1]  # RGB->BGR

        ocr = self._get_ocr()
        result = ocr.ocr(arr, cls=True)

        # ✅ Standardized lines output (array of objects)
        lines_objs: List[Dict[str, Any]] = []
        lines_text: List[str] = []
        confs: List[float] = []
        boxes_out: List[List[List[int]]] = []

        # Paddle returns: [ [ [box], (text, conf) ], ... ] per page
        if result and isinstance(result, list):
            page0 = result[0] if len(result) > 0 else []
            if page0 and isinstance(page0, list):
                for item in page0:
                    if not item or len(item) < 2:
                        continue

                    box = item[0]
                    txt_conf = item[1]

                    if not isinstance(txt_conf, (list, tuple)) or len(txt_conf) < 2:
                        continue

                    text = str(txt_conf[0]).strip()
                    try:
                        conf = float(txt_conf[1])
                    except Exception:
                        conf = 0.0

                    # box points -> ints
                    pts: List[List[int]] = []
                    if isinstance(box, list):
                        for pt in box:
                            if isinstance(pt, (list, tuple)) and len(pt) == 2:
                                pts.append([int(pt[0]), int(pt[1])])

                    if text:
                        lines_text.append(text)
                        confs.append(conf)
                        if pts:
                            boxes_out.append(pts)

                        # ✅ each line as object
                        lines_objs.append(
                            {
                                "text": text,
                                "score": conf,
                                "box": pts if pts else None,
                            }
                        )

        extracted_text = "\n".join(lines_text).strip()
        latency_ms = int((time.time() - t0) * 1000)

        avg_conf = float(sum(confs) / len(confs)) if confs else 0.0

        return {
            "model": self.name,
            "latency_ms": latency_ms,
            "latency": latency_ms,
            "filename": filename,
            "mime_type": mime_type,
            "text": extracted_text,

            # ✅ IMPORTANT: frontend expects `lines` as array
            "lines": lines_objs,

            # Optional numeric convenience
            "line_count": len(lines_objs),

            "chars": len(extracted_text),
            "avg_conf": avg_conf,

            # keep debug raw
            "raw": {
                "lines_text": lines_text,
                "boxes": boxes_out,
                "confs": confs,
                "paddle_raw": result,
            },
        }