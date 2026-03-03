import time
import io
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from app.adapters.base import OCRAdapter
from .postprocess_markdown import normalize_to_markdown


Token = Tuple[str, float, float, float, float]  # (text, x1, y1, x2, y2)


class PaddleOCRAdapter(OCRAdapter):
    def __init__(self):
        self._ocr = None

    @property
    def name(self) -> str:
        return "paddleocr"

    def _get_ocr(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR
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
            for k in ("file_bytes", "bytes", "image", "content", "data"):
                if k in kwargs and kwargs[k] is not None:
                    image_bytes = kwargs[k]
                    break
        if image_bytes is None:
            raise RuntimeError("PaddleOCRAdapter.run() did not receive image bytes")

        mt = (mime_type or "").strip().lower()

        # IMPORTANT:
        # main.py already converts PDF -> PNG for IMG_ONLY_MODELS.
        # So adapters should NOT do PDF conversion again.

        t0 = time.time()

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)[:, :, ::-1]  # RGB->BGR

        ocr = self._get_ocr()
        result = ocr.ocr(arr, cls=True)

        lines_objs: List[Dict[str, Any]] = []
        lines_text: List[str] = []
        confs: List[float] = []
        boxes_out: List[List[List[int]]] = []
        tokens: List[Token] = []

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

                    pts: List[List[int]] = []
                    if isinstance(box, list):
                        for pt in box:
                            if isinstance(pt, (list, tuple)) and len(pt) == 2:
                                pts.append([int(pt[0]), int(pt[1])])

                    if not text:
                        continue

                    lines_text.append(text)
                    confs.append(conf)

                    if pts:
                        boxes_out.append(pts)
                        try:
                            xs = [p[0] for p in pts]
                            ys = [p[1] for p in pts]
                            x1, x2 = float(min(xs)), float(max(xs))
                            y1, y2 = float(min(ys)), float(max(ys))
                            tokens.append((text, x1, y1, x2, y2))
                        except Exception:
                            pass

                    lines_objs.append(
                        {
                            "text": text,
                            "score": conf,
                            "box": pts if pts else None,
                        }
                    )

        extracted_plain = "\n".join(lines_text).strip()
        extracted_text = normalize_to_markdown(extracted_plain, tokens=tokens)

        latency_ms = int((time.time() - t0) * 1000)
        avg_conf = float(sum(confs) / len(confs)) if confs else 0.0

        return {
            "model": self.name,
            "latency_ms": latency_ms,
            "latency": latency_ms,
            "filename": filename,
            "mime_type": mt,
            "text": extracted_text,
            "lines": lines_objs,
            "line_count": len(lines_objs),
            "chars": len(extracted_text),
            "avg_conf": avg_conf,
            "raw": {
                "lines_text": lines_text,
                "boxes": boxes_out,
                "confs": confs,
                # NOTE: paddle_raw removed because it can be HUGE and slows JSON
                # If you want it back, add env flag later.
            },
        }

