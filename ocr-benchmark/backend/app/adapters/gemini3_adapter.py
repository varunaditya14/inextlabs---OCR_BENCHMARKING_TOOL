# ocr-benchmark/backend/app/adapters/gemini3_adapter.py

import os
import time
import base64
import json
from typing import Any, Dict

import requests

from .base import OCRAdapter


def _clean_ocr_text(s: str) -> str:
    """Remove common markdown/code-fence noise if model returns it."""
    if not s:
        return ""
    s = s.strip()

    # If the model wrapped output in ```...```, extract inside
    if "```" in s:
        parts = s.split("```")
        # Heuristic: take the biggest middle block
        if len(parts) >= 3:
            middle = max(parts[1:-1], key=len).strip()
            # Strip optional language tag like "markdown\n"
            middle_lines = middle.splitlines()
            if middle_lines and middle_lines[0].strip().isalpha():
                middle = "\n".join(middle_lines[1:]).strip()
            s = middle

    # Remove stray triple backticks if any remain
    s = s.replace("```", "").strip()

    # Remove repeated single-word junk lines sometimes returned
    junk = {"markdown", "json", "text"}
    lines = []
    for ln in s.splitlines():
        t = ln.strip()
        if t.lower() in junk and len(t) <= 12:
            continue
        lines.append(ln.rstrip())

    return "\n".join(lines).strip()


class Gemini3Adapter(OCRAdapter):
    """
    Gemini 3 OCR adapter (REST):
    - Sends image/PDF bytes to Gemini API with inlineData
    - Hard timeouts so backend never hangs forever
    - Retries for transient network stalls
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing in environment (.env).")

        # Default to your current choice; you can override via .env
        self.model_id = os.getenv("GEMINI_MODEL_ID", "gemini-3-flash-preview").strip()
        self.api_key = api_key

        # Hard timeouts (connect, read)
        self.connect_timeout = float(os.getenv("GEMINI_CONNECT_TIMEOUT", "10"))
        self.read_timeout = float(os.getenv("GEMINI_READ_TIMEOUT", "60"))

        # Retries
        self.max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

    def run(self, image_bytes: bytes, mime_type: str, filename: str = "", **kwargs) -> Dict[str, Any]:
        t0 = time.time()

        # Gemini accepts image/* and application/pdf
        if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
            raise ValueError(f"Gemini3 expects image/* or application/pdf. Got: {mime_type}")

        # Base64 encode file
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "You are an OCR engine.\n"
            "Task: Extract ALL visible text from the document EXACTLY as it appears.\n"
            "Rules:\n"
            "1) Output ONLY the extracted text.\n"
            "2) Do NOT include markdown.\n"
            "3) Do NOT include code fences like ```.\n"
            "4) Preserve line breaks.\n"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": mime_type, "data": b64}},
                        {"text": prompt},
                    ],
                }
            ],
            # Keep deterministic OCR-ish output
            "generationConfig": {
                "temperature": 0.0,
                "topP": 1.0,
                "maxOutputTokens": 4096,
            },
        }

        last_err = None
        raw_data: Dict[str, Any] = {}

        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    timeout=(self.connect_timeout, self.read_timeout),
                )
                # Handle quota/auth errors clearly
                if resp.status_code >= 400:
                    try:
                        raw_data = resp.json()
                    except Exception:
                        raw_data = {"status_code": resp.status_code, "text": resp.text}
                    raise RuntimeError(f"Gemini HTTP {resp.status_code}: {raw_data}")

                raw_data = resp.json()

                # Parse best text
                text = ""
                candidates = raw_data.get("candidates") or []
                if candidates:
                    content = (candidates[0].get("content") or {})
                    parts = content.get("parts") or []
                    # Some responses put text in parts[].text
                    texts = []
                    for p in parts:
                        if isinstance(p, dict) and "text" in p:
                            texts.append(p["text"])
                    text = "\n".join(texts).strip()

                text = _clean_ocr_text(text)

                latency_ms = int((time.time() - t0) * 1000)

                return {
                    "model": "gemini3",
                    "filename": filename,
                    "mime_type": mime_type,
                    "backend_latency_ms": latency_ms,
                    "latency_ms": latency_ms,
                    "text": text,
                    "raw": raw_data,   # keep for debugging
                    "lines": [],       # Gemini doesn't return boxes in this setup
                }

            except Exception as e:
                last_err = e
                # small backoff before retry
                time.sleep(0.6 * (attempt + 1))

        latency_ms = int((time.time() - t0) * 1000)
        raise RuntimeError(f"Gemini OCR failed after retries ({latency_ms} ms): {last_err}")
