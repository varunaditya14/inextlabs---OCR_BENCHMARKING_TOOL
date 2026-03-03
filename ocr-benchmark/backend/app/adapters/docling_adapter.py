import time
import tempfile
from pathlib import Path
from typing import Any, Dict

from .base import OCRAdapter


class DoclingAdapter(OCRAdapter):
    """
    Docling converts PDFs/images/docs into structured document -> export markdown.
    We'll write upload bytes to a temp file and run Docling on that path.
    """

    def __init__(self):
        # Lazy import so backend boots even if docling not installed yet
        from docling.document_converter import DocumentConverter  # noqa

        self._converter = DocumentConverter()

    def run(self, *, filename: str, mime_type: str, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        from docling.document_converter import DocumentConverter  # noqa

        t0 = time.time()

        suffix = Path(filename).suffix
        if not suffix:
            # fallback based on mime
            if mime_type == "application/pdf":
                suffix = ".pdf"
            elif mime_type.startswith("image/"):
                suffix = ".png"
            else:
                suffix = ".bin"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            result = self._converter.convert(tmp_path)
            md = result.document.export_to_markdown()
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

        latency_ms = int((time.time() - t0) * 1000)
        return {
            "text": md or "",
            "latency_ms": latency_ms,
            "raw": {
                "engine": "docling",
                "input_mime": mime_type,
            },
        }

