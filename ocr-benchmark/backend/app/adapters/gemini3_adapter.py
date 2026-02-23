import os
import time
import base64
from typing import Any, Dict, List

import requests

from .base import OCRAdapter
from .postprocess_markdown import normalize_to_markdown


def _clean_ocr_text(s: str) -> str:
    """
    Keep as a safety-net: Gemini sometimes returns fences or extra labels.
    We'll still prefer markdown output, but we remove junk if it appears.
    """
    if not s:
        return ""
    s = s.strip()

    # remove code fences blocks but keep inner content
    if "```" in s:
        parts = s.split("```")
        if len(parts) >= 3:
            middle = max(parts[1:-1], key=len).strip()
            middle_lines = middle.splitlines()
            if middle_lines and middle_lines[0].strip().isalpha():
                middle = "\n".join(middle_lines[1:]).strip()
            s = middle
    s = s.replace("```", "").strip()

    # remove tiny "markdown/json/text" labels
    junk = {"markdown", "json", "text"}
    lines = []
    for ln in s.splitlines():
        t = ln.strip()
        if t.lower() in junk and len(t) <= 12:
            continue
        lines.append(ln.rstrip())

    # remove common prefaces Gemini adds
    prefixes = (
        "here is the extracted text",
        "extracted text",
        "ocr output",
        "output",
        "result",
    )
    while lines and lines[0].strip().lower().rstrip(":") in prefixes:
        lines = lines[1:]

    return "\n".join(lines).strip()


def _text_to_lines(text: str) -> List[Dict[str, Any]]:
    """
    Frontend expects lines to be an array of objects.
    We keep it simple: split by newline.
    """
    if not text:
        return []
    t = str(text).replace("\r", "").strip()
    if not t:
        return []
    parts = [ln.rstrip() for ln in t.split("\n")]
    parts = [ln for ln in parts if ln.strip()]
    return [{"text": ln, "score": None, "box": None} for ln in parts]


class Gemini3Adapter(OCRAdapter):
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing in environment (.env).")

        self.model_id = os.getenv("GEMINI_MODEL_ID", "gemini-3-flash-preview").strip()
        self.api_key = api_key

        self.connect_timeout = float(os.getenv("GEMINI_CONNECT_TIMEOUT", "10"))
        self.read_timeout = float(os.getenv("GEMINI_READ_TIMEOUT", "80"))  # slightly more for PDFs
        self.max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

    def run(self, image_bytes: bytes, mime_type: str, filename: str = "", **kwargs) -> Dict[str, Any]:
        t0 = time.time()

        if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
            raise ValueError(f"Gemini3 expects image/* or application/pdf. Got: {mime_type}")

        b64 = base64.b64encode(image_bytes).decode("utf-8")

        # ✅ Prompt engineered for structure (Markdown tables) + strict output rules
        prompt = (
            "You are a high-accuracy OCR engine.\n"
            "Extract ALL visible text from the document.\n\n"
            "OUTPUT FORMAT (VERY IMPORTANT):\n"
            "- Output MUST be ONLY the extracted content.\n"
            "- Use Markdown to preserve structure:\n"
            "  * Use headings for section titles when present.\n"
            "  * If there is a table (invoice items, totals, etc.), output it as a proper Markdown table with | pipes.\n"
            "  * Preserve line breaks.\n"
            "- Do NOT add any commentary, explanations, or analysis.\n"
            "- Do NOT say 'here is the extracted text'.\n"
            "- Do NOT use code fences (no ```).\n\n"
            "QUALITY RULES:\n"
            "- Keep numbers exactly as seen (including commas and decimals).\n"
            "- Keep labels and values on the same line when they appear that way.\n"
            "- If a field is missing/unclear, omit it (do not hallucinate).\n"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime_type, "data": b64}},
                    ],
                }
            ],
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

                if resp.status_code >= 400:
                    try:
                        raw_data = resp.json()
                    except Exception:
                        raw_data = {"status_code": resp.status_code, "text": resp.text}
                    raise RuntimeError(f"Gemini HTTP {resp.status_code}: {raw_data}")

                raw_data = resp.json()

                text = ""
                candidates = raw_data.get("candidates") or []
                if candidates:
                    content = (candidates[0].get("content") or {})
                    parts = content.get("parts") or []
                    texts = []
                    for p in parts:
                        if isinstance(p, dict) and "text" in p:
                            texts.append(p["text"])
                    text = "\n".join(texts).strip()

                # Safety cleanup (if Gemini still adds junk)
                text = _clean_ocr_text(text)

                # ✅ Normalize to Markdown-friendly (strip tags, etc.)
                # (No tokens for Gemini in current adapter, so we pass only text.)
                text = normalize_to_markdown(text)

                lines = _text_to_lines(text)

                latency_ms = int((time.time() - t0) * 1000)

                return {
                    "model": "gemini3",
                    "filename": filename,
                    "mime_type": mime_type,
                    "backend_latency_ms": latency_ms,
                    "latency_ms": latency_ms,
                    "text": text,            # ✅ markdown structured now
                    "lines": lines,          # ✅ frontend expects array
                    "line_count": len(lines),
                    "raw": raw_data,
                }

            except Exception as e:
                last_err = e
                time.sleep(0.6 * (attempt + 1))

        latency_ms = int((time.time() - t0) * 1000)
        raise RuntimeError(f"Gemini OCR failed after retries ({latency_ms} ms): {last_err}")