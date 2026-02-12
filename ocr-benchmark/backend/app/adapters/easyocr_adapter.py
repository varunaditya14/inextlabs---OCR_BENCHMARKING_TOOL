import time
from typing import Any, Dict, Optional

import fitz  # PyMuPDF
from PIL import Image
import io

import easyocr
import numpy as np

from .base import OCRAdapter


def _pdf_first_page_to_png_bytes(pdf_bytes: bytes, zoom: float = 2.0) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.page_count == 0:
        raise RuntimeError("PDF has 0 pages")
    page = doc.load_page(0)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


class EasyOCRAdapter(OCRAdapter):
    def __init__(self):
        # keep it simple; you can add more languages later
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
        # accept bytes from various keys (depending on how main.py calls)
        if image_bytes is None:
            for key in ("file_bytes", "bytes", "image", "content", "data"):
                if key in kwargs and kwargs[key] is not None:
                    image_bytes = kwargs[key]
                    break

        if image_bytes is None:
            raise RuntimeError(f"EasyOCRAdapter.run() did not receive bytes. keys={list(kwargs.keys())}")

        mt = (mime_type or "").strip().lower()

        # ✅ if PDF -> convert first page to PNG
        if mt == "application/pdf" or (filename.lower().endswith(".pdf")):
            image_bytes = _pdf_first_page_to_png_bytes(image_bytes)
            mt = "image/png"

        t0 = time.time()

        # decode image bytes -> numpy
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = np.array(pil_img)

        results = self.reader.readtext(img)

        # build a simple unified output
        lines = []
        text_chunks = []
        for (bbox, txt, conf) in results:
            text_chunks.append(txt)
            lines.append({"text": txt, "score": float(conf), "bbox": bbox})

        extracted_text = "\n".join(text_chunks)
        latency_ms = (time.time() - t0) * 1000.0

        return {
            "model": self.name,
            "filename": filename,
            "mime_type": mt,
            "backend_latency_ms": latency_ms,
            "latency_ms": latency_ms,
            "raw": results,          # keep original easyocr output
            "text": extracted_text,  # extracted text shown in UI
            "lines": lines,          # enables “lines” metric in frontend
        }
