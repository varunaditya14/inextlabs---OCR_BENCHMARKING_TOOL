import io
import os
import time
import warnings
from typing import Any, Dict, List

from PIL import Image

from .postprocess_markdown import normalize_to_markdown

# Silence noisy libs
warnings.filterwarnings("ignore")

try:
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel, logging as hf_logging
    hf_logging.set_verbosity_error()
except Exception as e:
    raise RuntimeError("transformers not installed. Install: pip install transformers") from e


class TrOCRAdapter:
    """
    TrOCR is best for line-level OCR.
    For full-page docs, we tile the image into chunks and OCR each chunk.
    """

    def __init__(self, model_name: str = "microsoft/trocr-base-printed"):
        self.model_name = model_name
        self.device = "cpu"  # keep CPU to avoid setup pain

        # Avoid HF symlink warnings on Windows
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

        self.processor = TrOCRProcessor.from_pretrained(self.model_name)
        self.model = VisionEncoderDecoderModel.from_pretrained(self.model_name)
        self.model.to(self.device)

    def _image_from_bytes(self, image_bytes: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return img

    def _tile_image(self, img: Image.Image, rows: int = 3, cols: int = 2, overlap: int = 30) -> List[Image.Image]:
        """
        Split page into tiles (rows x cols) with small overlap, improves full-doc OCR.
        """
        w, h = img.size
        tile_w = w // cols
        tile_h = h // rows

        tiles = []
        for r in range(rows):
            for c in range(cols):
                left = max(0, c * tile_w - overlap)
                upper = max(0, r * tile_h - overlap)
                right = min(w, (c + 1) * tile_w + overlap)
                lower = min(h, (r + 1) * tile_h + overlap)
                tiles.append(img.crop((left, upper, right, lower)))
        return tiles

    def _ocr_one(self, img: Image.Image) -> str:
        pixel_values = self.processor(images=img, return_tensors="pt").pixel_values.to(self.device)
        generated_ids = self.model.generate(pixel_values, max_length=128)
        text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return (text or "").strip()

    def _dedupe_lines(self, lines: List[str]) -> List[str]:
        """
        Overlap tiling often repeats lines. This removes consecutive duplicates
        and near-empty noise.
        """
        out: List[str] = []
        last = ""
        for ln in lines:
            t = " ".join((ln or "").split()).strip()
            if not t:
                continue
            if t == last:
                continue
            out.append(ln.strip())
            last = t
        return out

    def run(self, image_bytes: bytes, filename: str = "", mime_type: str = "") -> Dict[str, Any]:
        t0 = time.time()

        img = self._image_from_bytes(image_bytes)

        # Tile full page → better doc OCR
        tiles = self._tile_image(img, rows=3, cols=2, overlap=40)

        parts: List[str] = []
        for tile in tiles:
            txt = self._ocr_one(tile)
            if txt:
                parts.append(txt)

        parts = self._dedupe_lines(parts)

        final_text = "\n".join(parts).strip()

        # ✅ keep formatting consistent across models
        final_text = normalize_to_markdown(final_text)

        latency_ms = (time.time() - t0) * 1000.0
        return {
            "model": "trocr",
            "text": final_text if final_text else "",
            "lines": [{"text": t, "score": None, "box": None} for t in (final_text.splitlines() if final_text else [])],
            "avg_conf": None,  # TrOCR doesn't give confidence easily
            "raw": {
                "model_name": self.model_name,
                "device": self.device,
                "tiles": len(tiles),
            },
            "latency_ms": latency_ms,
        }