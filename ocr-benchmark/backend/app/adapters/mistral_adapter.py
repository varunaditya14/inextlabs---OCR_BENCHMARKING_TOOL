import os
import time
import base64
import requests
from typing import Any, Dict, Optional, List

from .base import OCRAdapter


def _clean_endpoint(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip().strip('"').strip("'")
    s = s.replace("%27", "").strip('"').strip("'")
    s = s.rstrip("/")
    return s


def _text_to_lines(text: str) -> List[Dict[str, Any]]:
    """
    Convert extracted text into standardized lines array.
    Keeps line breaks; filters empty lines.
    """
    if not text:
        return []
    t = str(text).replace("\r", "").strip()
    if not t:
        return []
    parts = [ln.strip() for ln in t.split("\n")]
    parts = [ln for ln in parts if ln]
    return [{"text": ln, "score": None, "box": None} for ln in parts]


class MistralOCRAdapter(OCRAdapter):
    """
    Calls Azure-hosted Mistral OCR endpoint.
    Needs backend/.env:
      MISTRAL_OCR_ENDPOINT
      MISTRAL_OCR_TOKEN
      MISTRAL_OCR_MODEL (optional)
    """

    def __init__(self):
        self.endpoint = _clean_endpoint(os.getenv("MISTRAL_OCR_ENDPOINT", ""))
        self.token = os.getenv("MISTRAL_OCR_TOKEN", "").strip().strip('"').strip("'")
        self.model = os.getenv("MISTRAL_OCR_MODEL", "mistral-document-ai-2505").strip().strip('"').strip("'")

        if not self.endpoint:
            raise RuntimeError("MISTRAL_OCR_ENDPOINT is missing in backend/.env")
        if not self.token:
            raise RuntimeError("MISTRAL_OCR_TOKEN is missing in backend/.env")

    @property
    def name(self) -> str:
        return "mistral"

    def run(
        self,
        image_bytes: Optional[bytes] = None,
        filename: str = "",
        mime_type: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        if image_bytes is None:
            for key in ("file_bytes", "bytes", "image", "content", "data"):
                if key in kwargs and kwargs[key] is not None:
                    image_bytes = kwargs[key]
                    break

        if image_bytes is None:
            raise RuntimeError(
                "MistralOCRAdapter.run() did not receive file bytes. "
                f"Got kwargs keys: {list(kwargs.keys())}"
            )

        t0 = time.time()

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = (mime_type or "").strip() or "image/png"

        if mime_type == "application/pdf":
            data_url = f"data:application/pdf;base64,{b64}"
        else:
            data_url = f"data:{mime_type};base64,{b64}"

        payload = {
            "model": self.model,
            "document": {"type": "document_url", "document_url": data_url},
            "include_image_base64": True,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        try:
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=120)
        except Exception as e:
            raise RuntimeError(f"Mistral OCR request failed: {repr(e)}")

        if resp.status_code >= 400:
            raise RuntimeError(f"Mistral OCR HTTP {resp.status_code}: {resp.text[:2000]}")

        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(f"Mistral OCR returned non-JSON response: {resp.text[:2000]}")

        latency_ms = int((time.time() - t0) * 1000)

        extracted_text = ""
        if isinstance(data, dict):
            pages = data.get("pages")
            if isinstance(pages, list):
                chunks: List[str] = []
                for p in pages:
                    if isinstance(p, dict):
                        md = p.get("markdown")
                        if isinstance(md, str) and md.strip():
                            chunks.append(md.strip())
                if chunks:
                    extracted_text = "\n\n".join(chunks)

            if not extracted_text:
                for k in ("text", "extracted_text", "content"):
                    v = data.get(k)
                    if isinstance(v, str) and v.strip():
                        extracted_text = v.strip()
                        break

        lines = _text_to_lines(extracted_text)

        return {
            "model": self.name,
            "filename": filename,
            "mime_type": mime_type,
            "backend_latency_ms": latency_ms,
            "latency_ms": latency_ms,
            "text": extracted_text,
            "lines": lines,                 # ✅ now correct for frontend
            "line_count": len(lines),
            "raw": data,
        }