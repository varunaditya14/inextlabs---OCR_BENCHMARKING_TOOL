import os
import time
from typing import Any, Dict

from .base import OCRAdapter
from google import genai


class Gemini3ProAdapter(OCRAdapter):
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing in environment (.env).")

        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-3-pro-preview"  # fixed to Pro

    def run(self, *, filename: str, mime_type: str, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        t0 = time.time()

        prompt = (
            "Extract all readable text from this document EXACTLY as it appears. "
            "Preserve line breaks. Do not add explanations."
        )

        contents = [
            {"inline_data": {"mime_type": mime_type, "data": image_bytes}},
            prompt,
        ]

        resp = self.client.models.generate_content(
            model=self.model_id,
            contents=contents,
        )

        text = getattr(resp, "text", "") or ""
        latency_ms = (time.time() - t0) * 1000.0

        return {
            "model": "gemini3pro",
            "filename": filename,
            "mime_type": mime_type,
            "backend_latency_ms": latency_ms,
            "latency_ms": latency_ms,
            "text": text,
            "raw": self._safe_raw(resp),
            "lines": [],
        }

    def _safe_raw(self, resp: Any) -> Dict[str, Any]:
        try:
            if hasattr(resp, "to_dict"):
                return resp.to_dict()
        except Exception:
            pass
        return {"repr": repr(resp)}
