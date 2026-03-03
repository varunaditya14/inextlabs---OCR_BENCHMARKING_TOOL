import time
from typing import Any, Dict, Optional, List, Tuple

from PIL import Image
import io

import easyocr
import numpy as np

from .base import OCRAdapter
from .postprocess_markdown import normalize_to_markdown


Token = Tuple[str, float, float, float, float]  # (text, x1, y1, x2, y2)


class EasyOCRAdapter(OCRAdapter):
    def __init__(self):
        # Lazy-ish init could be added later; keep stable for now
        self.reader = easyocr.Reader(["en"], gpu=False)

    @property
    def name(self) -> str:
        return "easyocr"

    def run(
        self,
        image_bytes: Optional[bytes] = None,
        filename: str = "",
        mime_type: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        # accept bytes from various keys
        if image_bytes is None:
            for key in ("file_bytes", "bytes", "image", "content", "data"):
                if key in kwargs and kwargs[key] is not None:
                    image_bytes = kwargs[key]
                    break

        if image_bytes is None:
            raise RuntimeError(
                f"EasyOCRAdapter.run() did not receive bytes. keys={list(kwargs.keys())}"
            )

        mt = (mime_type or "").strip().lower()

        # IMPORTANT:
        # main.py already converts PDF -> PNG for IMG_ONLY_MODELS.
        # So adapters should NOT do PDF conversion again.

        t0 = time.time()

        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(pil_img)

        results = self.reader.readtext(img)

        lines = []
        text_chunks: List[str] = []
        tokens: List[Token] = []

        for (bbox, txt, conf) in results:
            txt = str(txt).strip()
            if not txt:
                continue

            text_chunks.append(txt)
            lines.append({"text": txt, "score": float(conf), "bbox": bbox})

            try:
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                x1, x2 = float(min(xs)), float(max(xs))
                y1, y2 = float(min(ys)), float(max(ys))
                tokens.append((txt, x1, y1, x2, y2))
            except Exception:
                pass

        extracted_plain = "\n".join(text_chunks).strip()
        extracted_text = normalize_to_markdown(extracted_plain, tokens=tokens)

        latency_ms = (time.time() - t0) * 1000.0

        return {
            "model": self.name,
            "filename": filename,
            "mime_type": mt,
            "backend_latency_ms": latency_ms,
            "latency_ms": latency_ms,
            "raw": results,
            "text": extracted_text,
            "lines": lines,
        }