import os
import time
import base64
import re
import requests
from typing import Any, Dict

from .base import OCRAdapter


def _clean_endpoint(raw: str) -> str:
    """
    Fix common endpoint copy/paste issues:
    - Removes surrounding quotes
    - Removes URL-encoded %27 (')
    - Removes trailing slashes
    """
    if not raw:
        return ""
    s = raw.strip().strip('"').strip("'")
    s = s.replace("%27", "").strip('"').strip("'")
    s = s.rstrip("/")
    return s


_TAG_RE = re.compile(r"</?[^>]+>")  # generic HTML/XML tags


def clean_mistral_markdown(md: str) -> str:
    """
    Mistral V2 sometimes returns HTML-ish tags inside markdown (ex: <b>Ship To</b>,
    <bbill to:="" to:=""></bill>). This function normalizes it into clean markdown.
    """
    if not md:
        return ""

    s = md

    # Normalize line endings
    s = s.replace("\r\n", "\n").replace("\r", "\n")

    # Common bold tags -> markdown bold
    s = re.sub(r"<\s*(b|strong)\s*>", "**", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*(b|strong)\s*>", "**", s, flags=re.IGNORECASE)

    # Fix weird "bill to" / "ship to" tag variants that show up in your sample
    # Examples:
    #   <bbill to:="" to:=""></bill>  -> **Bill To:**
    #   <b>Ship To:</b>              -> **Ship To:**
    s = re.sub(r"<\s*b+\s*bill\s*to[^>]*>", "**Bill To:**\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*/\s*b+\s*>", "**", s, flags=re.IGNORECASE)  # just in case

    # Convert <br> to new line (if it appears)
    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.IGNORECASE)

    # Remove any leftover tags completely
    s = _TAG_RE.sub("", s)

    # Cleanup: collapse too many blank lines
    s = re.sub(r"\n{3,}", "\n\n", s).strip()

    return s


class MistralV2Adapter(OCRAdapter):
    """
    Azure AI Foundry / Mistral Document AI V2 adapter.
    Returns clean markdown in result["text"] for your frontend renderer.
    """

    def __init__(self):
        self.api_key = os.getenv("MISTRALV2_API_KEY", "").strip()
        self.endpoint = _clean_endpoint(os.getenv("MISTRALV2_ENDPOINT", "").strip())
        self.model_id = os.getenv("MISTRALV2_MODEL", "mistral-document-ai-2512").strip()

        if not self.api_key:
            raise RuntimeError("MISTRALV2_API_KEY missing in backend .env")
        if not self.endpoint:
            raise RuntimeError("MISTRALV2_ENDPOINT missing in backend .env")

    def run(self, *, filename: str, mime_type: str, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        """
        NOTE: main.py passes `image_bytes` even for PDFs. Here it's just "file bytes".
        We send it to Mistral as a data URL base64 (like your curl sample).
        """
        t0 = time.time()

        # Build data URL (pdf or image)
        # Mistral sample says base64 only, document_url not supported. So we use data URL.
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.model_id,
            "document": {
                "type": "document_url",
                "document_url": data_url,
            },
            # If your endpoint supports "document_annotation" features later, you can add here.
        }

        try:
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=120)
        except Exception as e:
            raise RuntimeError(f"MistralV2 request failed: {e}") from e

        latency_ms = int((time.time() - t0) * 1000)

        if resp.status_code >= 400:
            raise RuntimeError(f"MistralV2 HTTP {resp.status_code}: {resp.text[:500]}")

        data = resp.json() if resp.content else {}

        # Mistral returns pages[].markdown (as seen in your network response)
        pages = data.get("pages", []) or []
        raw_md_pages = []
        for p in pages:
            md = p.get("markdown", "") or ""
            if md.strip():
                raw_md_pages.append(md)

        raw_md = "\n\n---\n\n".join(raw_md_pages).strip()

        # Clean it so your UI shows structured markdown (no <b...> garbage)
        cleaned_md = clean_mistral_markdown(raw_md)

        return {
            "text": cleaned_md,          # ✅ THIS is what your ExtractedTextBox should render
            "latency_ms": latency_ms,    # frontend uses this
            "raw": data,                 # keep full response for JSON download
        }