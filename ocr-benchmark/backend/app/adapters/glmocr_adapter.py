import base64
import re
import time
import requests
from typing import Any, Dict, List

from PIL import Image
from io import BytesIO

from .base import OCRAdapter


def _clean_ocr_text(s: str) -> str:
    s = (s or "").strip()

    blocks = re.findall(r"```(?:\w+)?\s*([\s\S]*?)\s*```", s)
    if blocks:
        s = "\n".join([b.strip() for b in blocks if b.strip()]).strip()

    s = s.replace("```", "").strip()

    lines = [ln.strip() for ln in s.splitlines()]
    junk = {"markdown", "json", "text"}
    lines = [ln for ln in lines if ln and ln.lower() not in junk]
    s = "\n".join(lines).strip()

    return s


def _text_to_lines(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    t = str(text).replace("\r", "").strip()
    if not t:
        return []
    parts = [ln.strip() for ln in t.split("\n")]
    parts = [ln for ln in parts if ln]
    return [{"text": ln, "score": None, "box": None} for ln in parts]


class GLMOCRAdapter(OCRAdapter):
    """
    Local GLM-OCR via Ollama.
    Requires: Ollama running at http://localhost:11434 and model 'glm-ocr' pulled.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")

    @property
    def name(self) -> str:
        return "glm-ocr"

    def run(self, image_bytes: bytes, mime_type: str, filename: str = "", **kwargs) -> Dict[str, Any]:
        if not (mime_type.startswith("image/") or mime_type == "application/octet-stream"):
            raise ValueError(f"GLM-OCR expects an image. Got mime_type={mime_type}")

        t0 = time.time()

        img = Image.open(BytesIO(image_bytes)).convert("RGB")

        max_side = 1280
        w, h = img.size
        scale = min(max_side / max(w, h), 1.0)

        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        image_bytes = buf.getvalue()

        img_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "You are an OCR engine.\n"
            "Task: Extract ALL visible text from the image.\n"
            "Output rules:\n"
            "1) Output ONLY the extracted text.\n"
            "2) Do NOT use markdown.\n"
            "3) Do NOT use code fences like ```.\n"
            "4) Do NOT output JSON.\n"
            "5) Preserve line breaks.\n"
        )

        payload = {
            "model": "glm-ocr",
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0},
            "keep_alive": "0",
        }

        resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=180)
        if not resp.ok:
            raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text}")

        data = resp.json()

        raw_text = data.get("response") or ""
        text = _clean_ocr_text(raw_text)

        latency_ms = int((time.time() - t0) * 1000)
        lines = _text_to_lines(text)

        return {
            "model": self.name,
            "filename": filename,
            "mime_type": mime_type,
            "backend_latency_ms": latency_ms,
            "latency_ms": latency_ms,
            "text": text,
            "lines": lines,          # ✅ now consistent
            "line_count": len(lines),
            "raw": data,
        }