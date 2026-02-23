import os
import time
from typing import Any, Dict, List

from .base import OCRAdapter
from .postprocess_markdown import normalize_to_markdown

from google import genai


def _clean_ocr_text(s: str) -> str:
    """
    Gemini sometimes adds prefaces or code fences.
    Keep it clean and only extracted content.
    """
    if not s:
        return ""
    s = str(s).strip()

    # remove common prefaces
    bad_prefixes = (
        "here is the extracted text",
        "extracted text",
        "ocr output",
        "output",
        "result",
    )
    lines = [ln.rstrip() for ln in s.splitlines()]

    # drop code fences but keep inner content if present
    if "```" in s:
        parts = s.split("```")
        if len(parts) >= 3:
            middle = max(parts[1:-1], key=len).strip()
            # drop an optional language marker
            middle_lines = middle.splitlines()
            if middle_lines and len(middle_lines[0].strip()) <= 12 and middle_lines[0].strip().isalpha():
                middle = "\n".join(middle_lines[1:]).strip()
            s = middle
            lines = [ln.rstrip() for ln in s.splitlines()]

    cleaned: List[str] = []
    for i, ln in enumerate(lines):
        t = ln.strip()
        if not t:
            cleaned.append("")  # keep blank lines
            continue
        low = t.lower().rstrip(":")
        if i == 0 and low in bad_prefixes:
            continue
        if low in {"markdown", "json", "text"} and len(t) <= 12:
            continue
        cleaned.append(ln.rstrip())

    return "\n".join(cleaned).strip()


def _text_to_lines(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    t = str(text).replace("\r", "").strip("\n")
    if not t.strip():
        return []
    parts = [ln.rstrip() for ln in t.split("\n")]
    parts = [ln for ln in parts if ln.strip()]
    return [{"text": ln, "score": None, "box": None} for ln in parts]


class Gemini3ProAdapter(OCRAdapter):
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing in environment (.env).")

        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-3-pro-preview"  # fixed to Pro

    def run(self, *, filename: str, mime_type: str, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        t0 = time.time()

        # ✅ Prompt engineered for structured output like Mistral
        prompt = (
            "You are a high-accuracy OCR engine.\n"
            "Extract ALL visible text from the document.\n\n"
            "OUTPUT FORMAT (VERY IMPORTANT):\n"
            "- Output MUST be ONLY the extracted content.\n"
            "- Use Markdown to preserve structure:\n"
            "  * Use headings for section titles if present.\n"
            "  * If there is any table (invoice items, totals, etc.), output it as a proper Markdown table with | pipes.\n"
            "  * Preserve line breaks.\n"
            "- Do NOT add commentary, explanations, or analysis.\n"
            "- Do NOT say 'here is the extracted text'.\n"
            "- Do NOT use code fences (no ```).\n"
            "- Do NOT output JSON.\n\n"
            "QUALITY RULES:\n"
            "- Keep numbers exactly as seen (commas/decimals/currency).\n"
            "- Do not hallucinate missing values.\n"
        )

        # NOTE: With the SDK, inline_data accepts bytes.
        contents = [
            {"inline_data": {"mime_type": mime_type, "data": image_bytes}},
            {"text": prompt},
        ]

        resp = self.client.models.generate_content(
            model=self.model_id,
            contents=contents,
        )

        text = getattr(resp, "text", "") or ""
        text = _clean_ocr_text(text)

        # ✅ Normalize to markdown-friendly output (tags cleanup, consistency)
        text = normalize_to_markdown(text)

        lines = _text_to_lines(text)
        latency_ms = (time.time() - t0) * 1000.0

        return {
            "model": "gemini3pro",
            "filename": filename,
            "mime_type": mime_type,
            "backend_latency_ms": latency_ms,
            "latency_ms": latency_ms,
            "text": text,                 # ✅ structured markdown now
            "raw": self._safe_raw(resp),
            "lines": lines,               # ✅ frontend consistent now
            "line_count": len(lines),
        }

    def _safe_raw(self, resp: Any) -> Dict[str, Any]:
        try:
            if hasattr(resp, "to_dict"):
                return resp.to_dict()
        except Exception:
            pass
        return {"repr": repr(resp)}