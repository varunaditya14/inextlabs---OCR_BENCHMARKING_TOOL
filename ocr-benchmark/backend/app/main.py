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

from app.billing import build_billing

# ✅ Reduce noisy logs (optional)
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# ✅ Load backend .env (located at ocr-benchmark/backend/.env)
BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=BACKEND_ENV)

print("ENV PATH:", BACKEND_ENV)
print("AZURE_OPENAI_API_KEY present?", bool(os.getenv("AZURE_OPENAI_API_KEY")))
print("AZURE_OPENAI_ENDPOINT:", os.getenv("AZURE_OPENAI_ENDPOINT"))
print("AZURE_OPENAI_DEPLOYMENT:", os.getenv("AZURE_OPENAI_DEPLOYMENT"))

# ===== Adapters =====
from app.adapters.easyocr_adapter import EasyOCRAdapter
from app.adapters.paddleocr_adapter import PaddleOCRAdapter
from app.adapters.mistral_adapter import MistralOCRAdapter
from app.adapters.gemini3_adapter import Gemini3Adapter
from app.adapters.gemini3pro_adapter import Gemini3ProAdapter
from app.adapters.trocr_adapter import TrOCRAdapter
from app.adapters.glmocr_adapter import GLMOCRAdapter
from app.adapters.gpt52_adapter import GPT52Adapter

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
    "gpt52": GPT52Adapter,
}

# ✅ Pretty labels for frontend dropdown
MODEL_LABELS = {
    "easyocr": "EasyOCR",
    "paddleocr": "PaddleOCR",
    "mistral": "Mistral OCR",
    "gemini3": "Gemini 3",
    "gemini3pro": "Gemini 3 Pro",
    "trocr": "TrOCR",
    "glm-ocr": "GLM OCR",
    "gpt52": "GPT 5.2",
}

# Models that require image bytes (if PDF uploaded -> convert first page to PNG)
IMG_ONLY_MODELS = {"easyocr", "paddleocr", "trocr", "gemini3", "gemini3pro", "glm-ocr", "gpt52"}

# ✅ Model categories for safe concurrency controls
API_MODELS = {"gemini3", "gemini3pro", "mistral", "glm-ocr", "gpt52"}  # network/rate-limited
HEAVY_LOCAL_MODELS = {"trocr"}  # heavy torch model

# ✅ Semaphores (tune these)
API_SEM = asyncio.Semaphore(2)     # allow only 2 API models at a time (avoid 429)
HEAVY_SEM = asyncio.Semaphore(1)   # avoid overloading TrOCR (GPU/CPU)

# ✅ Reuse adapter instances
_ADAPTER_INSTANCES: Dict[str, Any] = {}


def get_adapter_instance(model: str):
    if model not in _ADAPTER_INSTANCES:
        _ADAPTER_INSTANCES[model] = ADAPTERS[model]()  # create once
    return _ADAPTER_INSTANCES[model]


def sanitize_for_json(obj: Any) -> Any:
    if isinstance(obj, (bytes, bytearray)):
        return base64.b64encode(bytes(obj)).decode("utf-8")

    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(x) for x in obj]

    mod = getattr(type(obj), "__module__", "")
    if str(mod).startswith("numpy") and hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            return str(obj)

    if str(mod).startswith("numpy") and hasattr(obj, "tolist"):
        try:
            return obj.tolist()
        except Exception:
            return str(obj)

    if isinstance(obj, Path):
        return str(obj)

    return obj


def pdf_first_page_to_png_bytes(pdf_bytes: bytes, dpi: int = 200) -> bytes:
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError("PyMuPDF not installed. Install: python -m pip install pymupdf") from e

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


@app.get("/models")
def list_models() -> List[Dict[str, str]]:
    return [{"id": k, "label": MODEL_LABELS.get(k, k)} for k in ADAPTERS.keys()]


@app.post("/run-benchmark")
async def run_benchmark(file: UploadFile = File(...)) -> Dict[str, Any]:
    file_bytes = await file.read()
    mime_type = (file.content_type or "").lower()
    filename = file.filename or ""

    png_bytes = None
    if mime_type == "application/pdf":
        png_bytes = pdf_first_page_to_png_bytes(file_bytes, dpi=200)

    async def run_one(model: str) -> Dict[str, Any]:
        t0 = time.time()

        try:
            adapter = get_adapter_instance(model)

            effective_bytes = file_bytes
            effective_mime = mime_type
            effective_filename = filename

            if mime_type == "application/pdf" and model in IMG_ONLY_MODELS:
                effective_bytes = png_bytes
                effective_mime = "image/png"
                effective_filename = (filename or "file.pdf") + " (page1).png"

            async def call_adapter():
                if hasattr(adapter, "run_async") and callable(getattr(adapter, "run_async")):
                    return await adapter.run_async(
                        image_bytes=effective_bytes,
                        filename=effective_filename,
                        mime_type=effective_mime,
                    )
                return await run_in_threadpool(
                    lambda: adapter.run(
                        image_bytes=effective_bytes,
                        filename=effective_filename,
                        mime_type=effective_mime,
                    )
                )

            if model in API_MODELS:
                async with API_SEM:
                    result = await call_adapter()
            elif model in HEAVY_LOCAL_MODELS:
                async with HEAVY_SEM:
                    result = await call_adapter()
            else:
                result = await call_adapter()

        except Exception as e:
            return sanitize_for_json(
                {
                    "model": model,
                    "filename": filename,
                    "mime_type": mime_type,
                    "error": repr(e),
                    "backend_latency_ms": int((time.time() - t0) * 1000),
                }
            )

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

    models = list(ADAPTERS.keys())
    results_list = await asyncio.gather(*(run_one(m) for m in models))

    results = {r.get("model", "unknown"): r for r in results_list}
    return {"filename": filename, "mime_type": mime_type, "results": results}


@app.post("/run-ocr")
async def run_ocr(
    model: str = Form(...),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    model = (model or "").strip().lower()
    if model not in ADAPTERS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

    adapter = ADAPTERS[model]()

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

