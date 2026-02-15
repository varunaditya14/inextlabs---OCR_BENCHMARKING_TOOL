# ocr-benchmark/backend/app/adapters/glmocr_adapter.py

import base64
import re
import time
import requests

from .base import OCRAdapter
from PIL import Image
from io import BytesIO



def _clean_ocr_text(s: str) -> str:
    """
    GLM-OCR sometimes wraps output in code fences like:
    ```markdown ... ```
    This function extracts the inner content and removes junk labels.
    """
    s = (s or "").strip()

    # Extract inside code fences if present
    blocks = re.findall(r"```(?:\w+)?\s*([\s\S]*?)\s*```", s)
    if blocks:
        s = "\n".join([b.strip() for b in blocks if b.strip()]).strip()

    # Remove any stray fences
    s = s.replace("```", "").strip()

    # Remove repeated standalone "markdown/json/text" lines
    lines = [ln.strip() for ln in s.splitlines()]
    junk = {"markdown", "json", "text"}
    lines = [ln for ln in lines if ln and ln.lower() not in junk]
    s = "\n".join(lines).strip()

    return s


class GLMOCRAdapter(OCRAdapter):
    """
    Local GLM-OCR via Ollama.
    Requires: Ollama running at http://localhost:11434 and model 'glm-ocr' pulled.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")

    def run(self, image_bytes: bytes, mime_type: str, filename: str = "", **kwargs) -> dict:
        # Expect image bytes. Backend should convert PDF->PNG for image-only models.
        if not (mime_type.startswith("image/") or mime_type == "application/octet-stream"):
            raise ValueError(f"GLM-OCR expects an image. Got mime_type={mime_type}")

        t0 = time.time()

        # Downscale big images to avoid Ollama/ggml crashes
        img = Image.open(BytesIO(image_bytes)).convert("RGB")

        max_side = 1280
        w, h = img.size
        scale = min(max_side / max(w, h), 1.0)

        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        image_bytes = buf.getvalue()


        # Base64 image for Ollama
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
            # reduce randomness + avoid keeping heavy context around
            "options": {"temperature": 0},
            "keep_alive": "0",
        }

        resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=180)
        if not resp.ok:
            # show real Ollama error message (helps debugging memory/payload issues)
            raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text}")

        data = resp.json()

        raw_text = data.get("response") or ""
        text = _clean_ocr_text(raw_text)

        latency_ms = int((time.time() - t0) * 1000)

        return {
            "text": text,
            "raw": data,
            "backend_latency_ms": latency_ms,
        }
