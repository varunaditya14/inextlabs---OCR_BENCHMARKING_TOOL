import os
import time
import base64
import requests
from typing import Any, Dict, List, Optional

from .base import OCRAdapter
from .postprocess_markdown import normalize_to_markdown


def _text_to_lines(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    t = str(text).replace("\r", "").strip("\n")
    if not t.strip():
        return []
    parts = [ln.rstrip() for ln in t.split("\n")]
    parts = [ln for ln in parts if ln.strip()]
    return [{"text": ln, "score": None, "box": None} for ln in parts]


def _extract_text_from_gemini_json(raw: Dict[str, Any]) -> str:
    if not isinstance(raw, dict):
        return ""
    cands = raw.get("candidates") or []
    if not cands or not isinstance(cands, list) or not isinstance(cands[0], dict):
        return ""
    content = cands[0].get("content") or {}
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts") or []
    if not isinstance(parts, list):
        return ""
    out = []
    for p in parts:
        if isinstance(p, dict) and isinstance(p.get("text"), str):
            out.append(p["text"])
    return "\n".join(out).strip()


def _clean_ocr_text(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""

    # remove code fences but keep inner content
    if "```" in s:
        parts = s.split("```")
        if len(parts) >= 3:
            middle = max(parts[1:-1], key=len).strip()
            ml = middle.splitlines()
            if ml and len(ml[0].strip()) <= 12 and ml[0].strip().isalpha():
                middle = "\n".join(ml[1:]).strip()
            s = middle
    s = s.replace("```", "").strip()

    # remove common prefaces
    bad = {
        "here is the extracted text",
        "extracted text",
        "ocr output",
        "output",
        "result",
    }
    lines = [ln.rstrip() for ln in s.splitlines()]
    while lines and lines[0].strip().lower().rstrip(":") in bad:
        lines = lines[1:]

    out = "\n".join(lines).strip()
    return out


def _looks_like_invoice(text: str) -> bool:
    t = (text or "").lower()
    return ("invoice" in t) or ("gst" in t) or ("bill to" in t) or ("ship to" in t)


def _has_markdown_table(text: str) -> bool:
    if not text:
        return False
    lines = [ln for ln in text.splitlines() if "|" in ln]
    return len(lines) >= 2


def _safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        j = resp.json()
        return j if isinstance(j, dict) else {"raw": j}
    except Exception:
        return {"status_code": resp.status_code, "text": resp.text[:2000]}


def _is_daily_free_tier_quota_429(err_json: Dict[str, Any]) -> bool:
    """
    Detects the specific case you are hitting:
    GenerateRequestsPerDayPerProjectPerModel-FreeTier / free_tier_requests
    """
    msg = ""
    try:
        msg = (err_json.get("error") or {}).get("message") or ""
    except Exception:
        msg = ""

    # Common signals in your error
    if "free_tier_requests" in msg:
        return True
    if "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in str(err_json):
        return True

    # Also check quota violations structure if present
    try:
        details = (err_json.get("error") or {}).get("details") or []
        for d in details:
            if isinstance(d, dict) and d.get("@type", "").endswith("QuotaFailure"):
                violations = d.get("violations") or []
                for v in violations:
                    qm = (v or {}).get("quotaMetric", "")
                    qid = (v or {}).get("quotaId", "")
                    if "free_tier_requests" in qm or "FreeTier" in qid:
                        return True
    except Exception:
        pass

    return False


class Gemini3Adapter(OCRAdapter):
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing in environment (.env).")

        # NOTE: your error shows model 'gemini-3-flash'. That means your env may be overriding this.
        self.model_id = os.getenv("GEMINI_MODEL_ID", "gemini-3-flash").strip()
        self.api_key = api_key

        self.connect_timeout = float(os.getenv("GEMINI_CONNECT_TIMEOUT", "10"))
        self.read_timeout = float(os.getenv("GEMINI_READ_TIMEOUT", "120"))

        # Retries only help for transient issues; daily quota won't recover by retrying.
        self.max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "1"))

        # IMPORTANT: second strict-table call burns extra quota.
        self.enable_table_retry = os.getenv("GEMINI_ENABLE_TABLE_RETRY", "0").strip() == "1"

        self._session = requests.Session()

    def _call(self, *, b64: str, mime_type: str, prompt: str) -> Dict[str, Any]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_id}:generateContent?key={self.api_key}"
        )

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
                # keep large if you want full tables; not the cause of 429
                "maxOutputTokens": 8192,
            },
        }

        resp = self._session.post(
            url,
            json=payload,
            timeout=(self.connect_timeout, self.read_timeout),
        )

        if resp.status_code >= 400:
            j = _safe_json(resp)

            # Fail-fast for daily free-tier quota exhaustion
            if resp.status_code == 429 and _is_daily_free_tier_quota_429(j):
                raise RuntimeError(
                    "Gemini daily free-tier quota exhausted for this model. "
                    "This is NOT token overflow and NOT a code crash. "
                    f"HTTP 429 details: {j}"
                )

            # For other errors, raise as-is (caller decides retry behavior)
            raise RuntimeError(f"Gemini HTTP {resp.status_code}: {j}")

        return resp.json()

    def run(self, image_bytes: bytes, mime_type: str, filename: str = "", **kwargs) -> Dict[str, Any]:
        t0 = time.time()

        if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
            raise ValueError(f"Gemini3 expects image/* or application/pdf. Got: {mime_type}")

        b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt1 = (
            "You are a high-accuracy OCR engine.\n"
            "Extract ALL visible text from the document.\n\n"
            "OUTPUT MUST BE ONLY EXTRACTED CONTENT (NO commentary).\n"
            "Use Markdown.\n"
            "Preserve line breaks.\n\n"
            "TABLES ARE MANDATORY:\n"
            "If there is any table (invoice items / totals), output a proper Markdown table using | pipes.\n"
            "Reconstruct columns logically even if borders are faint.\n"
            "Do NOT omit the line-items table.\n"
        )

        last_err: Optional[Exception] = None
        raw1: Dict[str, Any] = {}

        for attempt in range(self.max_retries + 1):
            try:
                raw1 = self._call(b64=b64, mime_type=mime_type, prompt=prompt1)
                text1 = _clean_ocr_text(_extract_text_from_gemini_json(raw1))
                text1 = normalize_to_markdown(text1)

                # OPTIONAL: strict table retry (disabled by default to save quota)
                if self.enable_table_retry and _looks_like_invoice(text1) and not _has_markdown_table(text1):
                    prompt2 = (
                        "OCR TASK (STRICT).\n"
                        "Extract EVERYTHING from the document.\n"
                        "You MUST include the full invoice line-items as a Markdown table.\n"
                        "Use this format:\n"
                        "| Item | Description | Qty | Rate | Amount |\n"
                        "|---|---|---:|---:|---:|\n"
                        "If columns differ, adapt, but keep a Markdown table.\n"
                        "Output ONLY extracted content.\n"
                    )
                    raw2 = self._call(b64=b64, mime_type=mime_type, prompt=prompt2)
                    text2 = _clean_ocr_text(_extract_text_from_gemini_json(raw2))
                    text2 = normalize_to_markdown(text2)

                    if len(text2) > len(text1):
                        text1 = text2
                        raw1 = {"first": raw1, "second": raw2}

                latency_ms = int((time.time() - t0) * 1000)
                lines = _text_to_lines(text1)

                return {
                    "model": "gemini3",
                    "filename": filename,
                    "mime_type": mime_type,
                    "backend_latency_ms": latency_ms,
                    "latency_ms": latency_ms,
                    "text": text1,
                    "lines": lines,
                    "line_count": len(lines),
                    "raw": {
                        "model_id": self.model_id,
                        "usageMetadata": raw1.get("usageMetadata"),
                        "promptFeedback": raw1.get("promptFeedback"),
                    },
                }

            except Exception as e:
                last_err = e

                # Fail-fast if quota exhausted message is present (no point sleeping)
                if "daily free-tier quota exhausted" in str(e).lower() or "free_tier_requests" in str(e):
                    break

                # Retry only for transient issues: keep small backoff
                time.sleep(0.4 * (attempt + 1))

        latency_ms = int((time.time() - t0) * 1000)
        raise RuntimeError(f"Gemini OCR failed after retries ({latency_ms} ms): {last_err}")

