# ocr-benchmark/backend/app/main.py

import time
import base64
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import os
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=BACKEND_ENV)

from app.adapters.easyocr_adapter import EasyOCRAdapter
from app.adapters.paddleocr_adapter import PaddleOCRAdapter
from app.adapters.mistral_adapter import MistralOCRAdapter
from app.adapters.gemini3_adapter import Gemini3Adapter
from app.adapters.gemini3pro_adapter import Gemini3ProAdapter
from app.adapters.trocr_adapter import TrOCRAdapter


app = FastAPI(title="OCR Benchmark Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADAPTERS = {
    "easyocr": EasyOCRAdapter(),
    "paddleocr": PaddleOCRAdapter(),
    "mistral": MistralOCRAdapter(),
    "gemini3": Gemini3Adapter(),         
    "gemini3pro": Gemini3ProAdapter(),   
    "trocr": TrOCRAdapter(),             

}

def sanitize_for_json(obj: Any) -> Any:
    """
    Convert numpy types / bytes / weird objects into JSON-safe Python types.
    This fixes: PydanticSerializationError: numpy.int32 not serializable
    """
    tname = type(obj).__name__
    mod = type(obj).__module__

    # bytes -> base64 string
    if isinstance(obj, (bytes, bytearray)):
        return base64.b64encode(bytes(obj)).decode("utf-8")

    # dict
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}

    # list/tuple/set
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(x) for x in obj]

    # numpy scalar
    if mod.startswith("numpy") and hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            return str(obj)

    # numpy array
    if mod.startswith("numpy") and hasattr(obj, "tolist"):
        try:
            return obj.tolist()
        except Exception:
            return str(obj)

    # Path -> string
    if tname in ("Path",):
        return str(obj)

    return obj


def pdf_first_page_to_png_bytes(pdf_bytes: bytes, dpi: int = 200) -> bytes:
    """
    Convert the FIRST PAGE of a PDF to PNG bytes.

    Uses PyMuPDF (fitz). We rasterize with a matrix based on DPI.
    72 DPI is the PDF default. So scale = dpi / 72.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError(
            "PyMuPDF not installed. Install: python -m pip install pymupdf"
        ) from e

    if not pdf_bytes:
        raise RuntimeError("Empty PDF bytes")

    doc = None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count == 0:
            raise RuntimeError("PDF has 0 pages")

        page = doc.load_page(0)

        zoom = float(dpi) / 72.0
        mat = fitz.Matrix(zoom, zoom)

        # alpha=False avoids transparent background issues
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")

    except Exception as e:
        raise RuntimeError(f"Failed to convert PDF to PNG: {e}") from e

    finally:
        if doc is not None:
            doc.close()

# API

@app.post("/run-ocr")
async def run_ocr(
    model: str = Form(...),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    model = (model or "").strip().lower()
    if model not in ADAPTERS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

    adapter = ADAPTERS[model]

    file_bytes = await file.read()
    mime_type = (file.content_type or "").lower()
    filename = file.filename or ""

    # If PDF and model is image-only, convert PDF -> PNG(page1)
    effective_bytes = file_bytes
    effective_mime = mime_type

    # ✅ image-only engines (need image bytes)
    IMG_ONLY_MODELS = {"easyocr", "paddleocr", "dummy", "trocr", "gemini3", "gemini3pro"}

    if mime_type == "application/pdf" and model in IMG_ONLY_MODELS:
        effective_bytes = pdf_first_page_to_png_bytes(file_bytes, dpi=200)
        effective_mime = "image/png"
        if filename:
            filename = filename + " (page1).png"

    t0 = time.time()
    try:
        result = adapter.run(
            image_bytes=effective_bytes,
            filename=filename,
            mime_type=effective_mime,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {repr(e)}")

    backend_latency_ms = int((time.time() - t0) * 1000)

    # Ensure frontend always gets these fields
    if isinstance(result, dict):
        result.setdefault("backend_latency_ms", backend_latency_ms)
        result.setdefault("model", model)
        result.setdefault("filename", filename)
        result.setdefault("mime_type", effective_mime)
    else:
        result = {
            "model": model,
            "filename": filename,
            "mime_type": effective_mime,
            "backend_latency_ms": backend_latency_ms,
            "raw": result,
        }

    return sanitize_for_json(result)
