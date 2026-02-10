from __future__ import annotations

from typing import Any, Dict

from .base import OCRAdapter


class DummyAdapter(OCRAdapter):
    def run(self, filename: str, file_bytes: bytes) -> Dict[str, Any]:
        return {
            "model": "dummy",
            "filename": filename,
            "text": "dummy output (OCR not installed yet)",
            "lines": [],
        }
