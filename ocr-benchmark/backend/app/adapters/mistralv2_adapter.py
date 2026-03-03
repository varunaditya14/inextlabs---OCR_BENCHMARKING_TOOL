import os
import time
import base64
import re
import requests
from typing import Any, Dict

from .base import OCRAdapter


def _clean_endpoint(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip().strip('"').strip("'")
    s = s.replace("%27", "").strip('"').strip("'")
    s = s.rstrip("/")
    return s


_TAG_RE = re.compile(r"</?[^>]+>")


def clean_mistral_markdown(md: str) -> str:
    if not md:
        return ""

    s = md
    s = s.replace("\r\n", "\n").replace("\r", "\n")

    s = re.sub(r"<\s*(b|strong)\s*>", "**", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*(b|strong)\s*>", "**", s, flags=re.IGNORECASE)

    s = re.sub(r"<\s*b+\s*bill\s*to[^>]*>", "**Bill To:**\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*b+\s*>", "**", s, flags=re.IGNORECASE)

    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.IGNORECASE)
    s = _TAG_RE.sub("", s)

    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


class MistralV2Adapter(OCRAdapter):
    def __init__(self):
        self.api_key = os.getenv("MISTRALV2_API_KEY", "").strip()
        self.endpoint = _clean_endpoint(os.getenv("MISTRALV2_ENDPOINT", "").strip())
        self.model_id = os.getenv("MISTRALV2_MODEL", "mistral-document-ai-2512").strip()

        if not self.api_key:
            raise RuntimeError("MISTRALV2_API_KEY missing in backend .env")
        if not self.endpoint:
            raise RuntimeError("MISTRALV2_ENDPOINT missing in backend .env")

        self._session = requests.Session()

    def run(self, *, filename: str, mime_type: str, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        t0 = time.time()

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.model_id,
            "document": {"type": "document_url", "document_url": data_url},
        }

        try:
            resp = self._session.post(self.endpoint, headers=headers, json=payload, timeout=120)
        except Exception as e:
            raise RuntimeError(f"MistralV2 request failed: {e}") from e

        latency_ms = int((time.time() - t0) * 1000)

        if resp.status_code >= 400:
            raise RuntimeError(f"MistralV2 HTTP {resp.status_code}: {resp.text[:500]}")

        data = resp.json() if resp.content else {}

        pages = data.get("pages", []) or []
        raw_md_pages = []
        for p in pages:
            md = p.get("markdown", "") or ""
            if md.strip():
                raw_md_pages.append(md)

        raw_md = "\n\n---\n\n".join(raw_md_pages).strip()
        cleaned_md = clean_mistral_markdown(raw_md)

        # Keep raw small (main.py also trims)
        raw_small = {
            "engine": "mistralv2",
            "model_id": self.model_id,
            "page_count": len(pages) if isinstance(pages, list) else None,
        }

        return {
            "text": cleaned_md,
            "latency_ms": latency_ms,
            "raw": raw_small,
        }

