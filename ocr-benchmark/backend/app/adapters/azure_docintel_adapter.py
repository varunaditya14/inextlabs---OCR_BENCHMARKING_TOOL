# ocr-benchmark/backend/app/adapters/azure_docintel_adapter.py

import os
from typing import Any, Dict, List

from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient

from .base import OCRAdapter


class AzureDocIntelAdapter(OCRAdapter):
    """
    Azure AI Document Intelligence OCR (prebuilt-read)
    Env:
      AZURE_DI_ENDPOINT
      AZURE_DI_KEY
      AZURE_DI_MODEL  (default: prebuilt-read)
    """

    def __init__(self):
        endpoint = os.getenv("AZURE_DI_ENDPOINT", "").strip()
        key = os.getenv("AZURE_DI_KEY", "").strip()
        self.model_id = os.getenv("AZURE_DI_MODEL", "prebuilt-read").strip() or "prebuilt-read"

        if not endpoint or not key:
            raise RuntimeError("AzureDocIntelAdapter missing AZURE_DI_ENDPOINT / AZURE_DI_KEY in backend .env")

        self.client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))

    def run(self, image_bytes: bytes, filename: str = "", mime_type: str = "") -> Dict[str, Any]:
        # Azure SDK accepts bytes directly
        poller = self.client.begin_analyze_document(
            model_id=self.model_id,
            document=image_bytes
        )
        result = poller.result()

        lines_out: List[Dict[str, Any]] = []
        full_text_parts: List[str] = []

        # result.pages -> each page has lines and words (words have confidence)
        for page in result.pages or []:
            # Build a word confidence map via spans is complex; simplest:
            # compute line confidence as average of word confidences that lie on that page
            # If words list exists:
            words = page.words or []
            avg_word_conf = None
            if words:
                avg_word_conf = sum((w.confidence or 0.0) for w in words) / max(len(words), 1)

            for ln in page.lines or []:
                txt = (ln.content or "").strip()
                if not txt:
                    continue

                full_text_parts.append(txt)

                # polygon is 8 numbers (x1,y1,...)
                bbox = None
                if ln.polygon:
                    pts = []
                    # ln.polygon is list of Points; each has x,y
                    for p in ln.polygon:
                        pts.append({"x": float(p.x), "y": float(p.y)})
                    bbox = pts

                lines_out.append({
                    "text": txt,
                    "bbox": bbox,
                    "confidence": float(avg_word_conf) if avg_word_conf is not None else None,
                    "page": int(page.page_number) if page.page_number is not None else None,
                })

        full_text = "\n".join(full_text_parts).strip()

        return {
            "text": full_text,
            "lines": lines_out,
            "raw": {
                "model_name": f"azure-doc-intel:{self.model_id}",
                "pages": len(result.pages or []),
            }
        }
