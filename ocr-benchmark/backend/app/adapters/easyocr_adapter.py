from __future__ import annotations

import io
from typing import Any, Dict, List

import numpy as np
from PIL import Image
import easyocr

from .base import OCRAdapter


def _to_py(obj: Any) -> Any:
    """Convert numpy/scalar/arrays to JSON-serializable Python types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (list, tuple)):
        return [_to_py(x) for x in obj]
    return obj


class EasyOCRAdapter(OCRAdapter):
    def __init__(self) -> None:
        self.reader = easyocr.Reader(["en"], gpu=False)

    def run(self, filename: str, file_bytes: bytes) -> Dict[str, Any]:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        img_np = np.array(img)

        result = self.reader.readtext(img_np)

        lines: List[Dict[str, Any]] = []
        full_text_parts: List[str] = []

        for box, text, conf in result:
            # box sometimes contains numpy int types -> convert
            box_py = _to_py(box)
            lines.append(
                {
                    "text": str(text),
                    "score": float(conf),
                    "box": box_py,
                }
            )
            full_text_parts.append(str(text))

        return {
            "model": "easyocr",
            "filename": filename,
            "text": "\n".join(full_text_parts),
            "lines": lines,
        }
