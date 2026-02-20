# ocr-benchmark/backend/app/main.py

import time
import base64
import os
import asyncio
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from starlette.concurrency import run_in_threadpool

# ✅ billing helper
from app.billing import build_billing

# ✅ Reduce noisy logs (optional)
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# ✅ Load backend .env (located at ocr-benchmark/backend/.env)
BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=BACKEND_ENV)

# ===== Adapters =====
from app.adapters.easyocr_adapter import EasyOCRAdapter
from app.adapters.paddleocr_adapter import PaddleOCRAdapter
from app.adapters.mistral_adapter import MistralOCRAdapter
from app.adapters.gemini3_adapter import Gemini3Adapter
from app.adapters.gemini3pro_adapter import Gemini3ProAdapter
from app.adapters.trocr_adapter import TrOCRAdapter
from app.adapters.glmocr_adapter import GLMOCRAdapter


app = FastAPI(title="OCR Benchmark Backend")

# ✅ CORS (frontend calls backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Registry of available models =====
ADAPTERS = {
    "easyocr": EasyOCRAdapter,
    "paddleocr": PaddleOCRAdapter,
    "mistral": MistralOCRAdapter,
    "gemini3": Gemini3Adapter,
    "gemini3pro": Gemini3ProAdapter,
    "trocr": TrOCRAdapter,
    "glm-ocr": GLMOCRAdapter,
}

# Models that require image bytes (if PDF uploaded -> convert first page to PNG)
IMG_ONLY_MODELS = {"easyocr", "paddleocr", "trocr", "gemini3", "gemini3pro", "glm-ocr"}

# ✅ Model categories for safe concurrency controls
API_MODELS = {"gemini3", "gemini3pro", "mistral", "glm-ocr"}  # network/rate-limited
HEAVY_LOCAL_MODELS = {"trocr"}  # heavy torch model

# ✅ Semaphores (tune these)
API_SEM = asyncio.Semaphore(2)     # allow only 2 API models at a time (avoid 429)
HEAVY_SEM = asyncio.Semaphore(1)   # avoid overloading TrOCR (GPU/CPU)

# ✅ Reuse adapter instances (prevents re-init overhead if adapters cache models internally)
_ADAPTER_INSTANCES: Dict[str, Any] = {}


def get_adapter_instance(model: str):
    if model not in _ADAPTER_INSTANCES:
        _ADAPTER_INSTANCES[model] = ADAPTERS[model]()  # create once
    return _ADAPTER_INSTANCES[model]


def sanitize_for_json(obj: Any) -> Any:
    """
    Convert numpy types / bytes / weird objects into JSON-safe Python types.
    Fixes: numpy.int32 not serializable etc.
    """
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
    tname = type(obj).__name__
    mod = getattr(type(obj), "__module__", "")
    if str(mod).startswith("numpy") and hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            return str(obj)

    # numpy array
    if str(mod).startswith("numpy") and hasattr(obj, "tolist"):
        try:
            return obj.tolist()
        except Exception:
            return str(obj)

    # Path -> string
    if isinstance(obj, Path):
        return str(obj)

    return obj


def pdf_first_page_to_png_bytes(pdf_bytes: bytes, dpi: int = 200) -> bytes:
    """
    Convert the FIRST PAGE of a PDF to PNG bytes.
    Uses PyMuPDF (fitz).
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError('PyMuPDF not installed. Install: python -m pip install pymupdf') from e

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

        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    except Exception as e:
        raise RuntimeError(f"Failed to convert PDF to PNG: {e}") from e
    finally:
        if doc is not None:
            doc.close()


# ✅ Frontend dropdown uses this
@app.get("/models")
def list_models() -> List[Dict[str, str]]:
    out = []
    for k in ADAPTERS.keys():
        out.append({"id": k, "label": k})
    return out


# =========================
# ✅ NEW FAST ENDPOINT
# =========================
@app.post("/run-benchmark")
async def run_benchmark(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Runs ALL models in one request, concurrently (safe controlled concurrency),
    and returns combined results for instant frontend switching.
    """
    file_bytes = await file.read()
    mime_type = (file.content_type or "").lower()
    filename = file.filename or ""

    png_bytes = None
    if mime_type == "application/pdf":
        # Convert once, reuse for image-only models
        png_bytes = pdf_first_page_to_png_bytes(file_bytes, dpi=200)

    async def run_one(model: str) -> Dict[str, Any]:
        adapter = get_adapter_instance(model)

        effective_bytes = file_bytes
        effective_mime = mime_type
        effective_filename = filename

        if mime_type == "application/pdf" and model in IMG_ONLY_MODELS:
            effective_bytes = png_bytes
            effective_mime = "image/png"
            effective_filename = (filename or "file.pdf") + " (page1).png"

        t0 = time.time()

        try:
            # API models: controlled concurrency + async if available
            if model in API_MODELS:
                async with API_SEM:
                    result = await adapter.run_async(
                        image_bytes=effective_bytes,
                        filename=effective_filename,
                        mime_type=effective_mime,
                    )

            # Heavy local model: controlled concurrency + threadpool
            elif model in HEAVY_LOCAL_MODELS:
                async with HEAVY_SEM:
                    result = await run_in_threadpool(
                        lambda: adapter.run(
                            image_bytes=effective_bytes,
                            filename=effective_filename,
                            mime_type=effective_mime,
                        )
                    )

            # Normal local OCR: run in threadpool so multiple can run together
            else:
                result = await run_in_threadpool(
                    lambda: adapter.run(
                        image_bytes=effective_bytes,
                        filename=effective_filename,
                        mime_type=effective_mime,
                    )
                )

        except Exception as e:
            # return error but do NOT crash whole benchmark
            return sanitize_for_json(
                {
                    "model": model,
                    "filename": effective_filename,
                    "mime_type": effective_mime,
                    "error": repr(e),
                    "backend_latency_ms": int((time.time() - t0) * 1000),
                }
            )

        backend_latency_ms = int((time.time() - t0) * 1000)

        # normalize fields
        if isinstance(result, dict):
            result.setdefault("backend_latency_ms", backend_latency_ms)
            result.setdefault("model", model)
            result.setdefault("filename", effective_filename)
            result.setdefault("mime_type", effective_mime)
        else:
            result = {
                "model": model,
                "filename": effective_filename,
                "mime_type": effective_mime,
                "backend_latency_ms": backend_latency_ms,
                "raw": result,
            }

        # attach billing
        result["billing"] = build_billing(
            model=model,
            payload=result,
            file_size_bytes=len(file_bytes) if file_bytes else 0,
        )

        return sanitize_for_json(result)

    models = list(ADAPTERS.keys())

    # run all models concurrently
    results_list = await asyncio.gather(*(run_one(m) for m in models))

    # return keyed results for frontend caching
    results = {}
    for r in results_list:
        k = r.get("model", "unknown")
        results[k] = r

    return {"filename": filename, "mime_type": mime_type, "results": results}


# =========================
# ✅ EXISTING SINGLE-MODEL ENDPOINT (keep it)
# =========================
@app.post("/run-ocr")
async def run_ocr(
    model: str = Form(...),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    model = (model or "").strip().lower()
    if model not in ADAPTERS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

    adapter_class = ADAPTERS[model]
    adapter = adapter_class()

    file_bytes = await file.read()
    mime_type = (file.content_type or "").lower()
    filename = file.filename or ""

    effective_bytes = file_bytes
    effective_mime = mime_type
    effective_filename = filename

    if mime_type == "application/pdf" and model in IMG_ONLY_MODELS:
        effective_bytes = pdf_first_page_to_png_bytes(file_bytes, dpi=200)
        effective_mime = "image/png"
        if effective_filename:
            effective_filename = effective_filename + " (page1).png"

    t0 = time.time()
    try:
        result = adapter.run(
            image_bytes=effective_bytes,
            filename=effective_filename,
            mime_type=effective_mime,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {repr(e)}")

    backend_latency_ms = int((time.time() - t0) * 1000)

    if isinstance(result, dict):
        result.setdefault("backend_latency_ms", backend_latency_ms)
        result.setdefault("model", model)
        result.setdefault("filename", effective_filename)
        result.setdefault("mime_type", effective_mime)
    else:
        result = {
            "model": model,
            "filename": effective_filename,
            "mime_type": effective_mime,
            "backend_latency_ms": backend_latency_ms,
            "raw": result,
        }

    result["billing"] = build_billing(
        model=model,
        payload=result,
        file_size_bytes=len(file_bytes) if file_bytes else 0,
    )

    return sanitize_for_json(result)