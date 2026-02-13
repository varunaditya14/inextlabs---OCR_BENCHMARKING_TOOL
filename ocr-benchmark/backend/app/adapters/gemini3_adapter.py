import os
import time
from typing import Any, Dict, Optional

from .base import OCRAdapter

# New unified SDK
from google import genai


class Gemini3Adapter(OCRAdapter):
    """
    Gemini 3 OCR-ish adapter:
    - Sends image OR PDF bytes to Gemini Developer API
    - Asks model to extract text faithfully
    - Returns our common response format: text + raw (+ empty lines for now)
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing in environment (.env).")

        self.client = genai.Client(api_key=api_key)

        # Default model if not provided
        self.model_id = os.getenv("GEMINI_MODEL_ID", "gemini-3-flash-preview").strip()

    def run(
        self,
        *,
        filename: str,
        mime_type: str,
        image_bytes: bytes,
        **kwargs,
    ) -> Dict[str, Any]:
        t0 = time.time()

        # Prompt tuned for OCR extraction
        prompt = (
            "Extract all readable text from this document EXACTLY as it appears. "
            "Preserve line breaks. Do not add explanations. "
            "If it's a form/table, keep the structure using plain text."
        )

        # Send file bytes inline (works for images + PDFs)
        # The SDK accepts multimodal parts; simplest is dict-like part with bytes.
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
            "model": "gemini3",
            "filename": filename,
            "mime_type": mime_type,
            "backend_latency_ms": latency_ms,
            "latency_ms": latency_ms,
            "text": text,
            "raw": self._safe_raw(resp),
            "lines": [],  # Gemini doesn't return boxes by default
        }

    def _safe_raw(self, resp: Any) -> Dict[str, Any]:
        # Keep raw response for debugging / transparency
        try:
            if hasattr(resp, "to_dict"):
                return resp.to_dict()
        except Exception:
            pass
        try:
            return {"repr": repr(resp)}
        except Exception:
            return {"repr": "unavailable"}
