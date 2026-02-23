import base64
import re
import time
import requests
from typing import Any, Dict, List

from PIL import Image
from io import BytesIO

from .base import OCRAdapter
from .postprocess_markdown import normalize_to_markdown


def _clean_ocr_text(s: str) -> str:
    s = (s or "").strip()

    # keep inner content of fenced blocks, if any
    blocks = re.findall(r"```(?:\w+)?\s*([\s\S]*?)\s*```", s)
    if blocks:
        s = "\n".join([b.strip() for b in blocks if b.strip()]).strip()

    s = s.replace("```", "").strip()

    # drop tiny labels
    lines = [ln.rstrip() for ln in s.splitlines()]
    junk = {"markdown", "json", "text"}
    lines2 = []
    for ln in lines:
        t = ln.strip()
        if not t:
            continue
        if t.lower() in junk and len(t) <= 12:
            continue
        # remove common prefaces
        low = t.lower().rstrip(":")
        if low in {"here is the extracted text", "extracted text", "ocr output", "output", "result"}:
            continue
        lines2.append(ln.rstrip())

    return "\n".join(lines2).strip()


def _text_to_lines(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    t = str(text).replace("\r", "").strip()
    if not t:
        return []
    parts = [ln.rstrip() for ln in t.split("\n")]
    parts = [ln for ln in parts if ln.strip()]
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
        # Your current flow expects GLM image only
        if not (mime_type.startswith("image/") or mime_type == "application/octet-stream"):
            raise ValueError(f"GLM-OCR expects an image. Got mime_type={mime_type}")

        t0 = time.time()

        img = Image.open(BytesIO(image_bytes)).convert("RGB")

        # shrink huge images (faster + less hallucination)
        max_side = 1280
        w, h = img.size
        scale = min(max_side / max(w, h), 1.0)

        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        image_bytes = buf.getvalue()

        img_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # ✅ Prompt engineered to produce structured Markdown like Mistral
        prompt = (
            "You are an OCR engine.\n"
            "Extract ALL visible text from the image.\n\n"
            "STRICT OUTPUT:\n"
            "- Output ONLY extracted content.\n"
            "- Use Markdown.\n"
            "- Never use code fences (```).\n"
            "- Never output JSON.\n"
            "- Never add commentary.\n\n"
            "TABLES (MANDATORY):\n"
            "If you see a table (like invoice items), you MUST output a Markdown table using pipes.\n"
            "Do NOT flatten it into plain text.\n\n"
            "For an invoice items table, use this exact column order if present:\n"
            "Sr | Description | HSN/SAC | Qty | Unit | Rate (₹) | Amount (₹)\n\n"
            "Example format (follow exactly):\n"
            "| Sr | Description | HSN/SAC | Qty | Unit | Rate (₹) | Amount (₹) |\n"
            "|---:|-------------|--------:|----:|------|---------:|-----------:|\n"
            "| 1 | ... | ... | ... | ... | ... | ... |\n"
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

        # ✅ normalize tags, remove junk, keep markdown-friendly output consistent
        text = normalize_to_markdown(text)

        latency_ms = int((time.time() - t0) * 1000)
        lines = _text_to_lines(text)

        return {
            "model": self.name,
            "filename": filename,
            "mime_type": mime_type,
            "backend_latency_ms": latency_ms,
            "latency_ms": latency_ms,
            "text": text,          # ✅ markdown structured now
            "lines": lines,        # ✅ now consistent
            "line_count": len(lines),
            "raw": data,
        }