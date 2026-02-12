from typing import Any, Dict, Optional
from .base import OCRAdapter

class DummyOCRAdapter(OCRAdapter):
    @property
    def name(self) -> str:
        return "dummy"

    def run(self, image_bytes: Optional[bytes] = None, filename: str = "", mime_type: str = "", **kwargs) -> Dict[str, Any]:
        return {
            "model": self.name,
            "latency_ms": 0,
            "raw": {},
            "text": "(dummy) no OCR performed",
            "lines": [],
        }
