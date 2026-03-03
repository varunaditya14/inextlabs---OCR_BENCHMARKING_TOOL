import time
import base64
import os
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool

from app.billing import build_billing

# Reduce noisy logs
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Load backend .env
BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=BACKEND_ENV)

# Optional debug prints (set DEBUG_ENV=1 to enable)
if os.getenv("DEBUG_ENV", "0").strip() == "1":
    print("ENV PATH:", BACKEND_ENV)
    print("AZURE_OPENAI_API_KEY present?", bool(os.getenv("AZURE_OPENAI_API_KEY")))
    print("AZURE_OPENAI_ENDPOINT:", os.getenv("AZURE_OPENAI_ENDPOINT"))
    print("AZURE_OPENAI_DEPLOYMENT:", os.getenv("AZURE_OPENAI_DEPLOYMENT"))
    print("MISTRALV2_API_KEY present?", bool(os.getenv("MISTRALV2_API_KEY")))
    print("MISTRALV2_ENDPOINT:", os.getenv("MISTRALV2_ENDPOINT"))
    print("GEMINI_API_KEY present?", bool(os.getenv("GEMINI_API_KEY")))

# ===== Adapters =====
from app.adapters.easyocr_adapter import EasyOCRAdapter
from app.adapters.paddleocr_adapter import PaddleOCRAdapter
from app.adapters.mistral_adapter import MistralOCRAdapter
from app.adapters.gemini3_adapter import Gemini3Adapter
from app.adapters.gemini3pro_adapter import Gemini3ProAdapter
from app.adapters.gpt52_adapter import GPT52Adapter
from app.adapters.mistralv2_adapter import MistralV2Adapter
from app.adapters.docling_adapter import DoclingAdapter
from app.adapters.markitdown_adapter import MarkItDownAdapter
from app.adapters.langextract_adapter import LangExtractAdapter

app = FastAPI(title="OCR Benchmark Backend")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_LABELS = {
    "easyocr": "EasyOCR",
    "paddleocr": "PaddleOCR",
    "mistral": "Mistral OCR",
    "mistralv2": "Mistral V2",
    "gemini3": "Gemini 3",
    "gemini3pro": "Gemini 3 Pro",
    "gpt52": "GPT 5.2",
    "docling": "Docling",
    "markitdown": "MarkItDown",
    "langextract": "LangExtract",
}

ADAPTERS = {
    "easyocr": EasyOCRAdapter,
    "paddleocr": PaddleOCRAdapter,
    "mistral": MistralOCRAdapter,
    "mistralv2": MistralV2Adapter,
    "gemini3": Gemini3Adapter,
    "gemini3pro": Gemini3ProAdapter,
    "gpt52": GPT52Adapter,
    "docling": DoclingAdapter,
    "markitdown": MarkItDownAdapter,
    "langextract": LangExtractAdapter,
}

# Models that require image bytes (if PDF uploaded -> convert first page to PNG)
# Docling/MarkItDown can take PDF directly -> keep them out.
IMG_ONLY_MODELS = {
    "easyocr",
    "paddleocr",
    "gemini3",
    "gemini3pro",
    "gpt52",
}

# Concurrency categories
API_MODELS = {
    "gemini3",
    "gemini3pro",
    "mistral",
    "mistralv2",
    "gpt52",
    "langextract",
}

HEAVY_LOCAL_MODELS = {
    "docling",
    "markitdown",
}

API_SEM = asyncio.Semaphore(int(os.getenv("API_SEM_LIMIT", "2")))
HEAVY_SEM = asyncio.Semaphore(int(os.getenv("HEAVY_SEM_LIMIT", "1")))

# Singleton adapters cache (prevents reloading models every request)
_ADAPTER_INSTANCES: Dict[str, Any] = {}


def get_adapter_instance(model: str):
    if model not in _ADAPTER_INSTANCES:
        _ADAPTER_INSTANCES[model] = ADAPTERS[model]()
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


async def run_one_model(
    model: str,
    file_bytes: bytes,
    mime_type: str,
    filename: str,
    png_bytes_map: Optional[Dict[str, bytes]] = None,
) -> Dict[str, Any]:
    t0 = time.time()

    effective_bytes = file_bytes
    effective_mime = mime_type
    effective_filename = filename

    try:
        adapter = get_adapter_instance(model)

        # Convert PDF -> PNG only for IMG_ONLY_MODELS
        if mime_type == "application/pdf" and model in IMG_ONLY_MODELS:
            if png_bytes_map is None:
                png_bytes_map = {"default": pdf_first_page_to_png_bytes(file_bytes, dpi=200)}
                # Optional hires for Gemini (can disable with ENABLE_GEMINI_HIRES=0)
                if os.getenv("ENABLE_GEMINI_HIRES", "1").strip() == "1":
                    png_bytes_map["hires"] = pdf_first_page_to_png_bytes(file_bytes, dpi=300)

            if model in {"gemini3", "gemini3pro"}:
                effective_bytes = png_bytes_map.get("hires") or png_bytes_map.get("default")
            else:
                effective_bytes = png_bytes_map.get("default")

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


@app.get("/models")
def list_models() -> List[Dict[str, str]]:
    return [{"id": k, "label": MODEL_LABELS.get(k, k)} for k in ADAPTERS.keys()]


@app.post("/run-benchmark")
async def run_benchmark(file: UploadFile = File(...)) -> Dict[str, Any]:
    file_bytes = await file.read()
    mime_type = (file.content_type or "").lower()
    filename = file.filename or ""

    # ---- PDF -> PNG cache (default + hires) ----
    png_bytes_map: Dict[str, bytes] = {}
    if mime_type == "application/pdf":
        png_bytes_map["default"] = pdf_first_page_to_png_bytes(file_bytes, dpi=200)
        if os.getenv("ENABLE_GEMINI_HIRES", "1").strip() == "1":
            png_bytes_map["hires"] = pdf_first_page_to_png_bytes(file_bytes, dpi=300)

    models = list(ADAPTERS.keys())
    results_list = await asyncio.gather(
        *(run_one_model(m, file_bytes, mime_type, filename, png_bytes_map) for m in models)
    )

    results: Dict[str, Any] = {}
    for r in results_list:
        results[r.get("model", "unknown")] = r

    return {"filename": filename, "mime_type": mime_type, "results": results}


@app.post("/run-ocr")
async def run_ocr(
    model: str = Form(...),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    model = (model or "").strip().lower()
    if model not in ADAPTERS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

    file_bytes = await file.read()
    mime_type = (file.content_type or "").lower()
    filename = file.filename or ""

    # cache conversions even for single model (prevents converting twice in logic)
    png_bytes_map: Dict[str, bytes] = {}
    if mime_type == "application/pdf":
        png_bytes_map["default"] = pdf_first_page_to_png_bytes(file_bytes, dpi=200)
        if os.getenv("ENABLE_GEMINI_HIRES", "1").strip() == "1":
            png_bytes_map["hires"] = pdf_first_page_to_png_bytes(file_bytes, dpi=300)

    result = await run_one_model(model, file_bytes, mime_type, filename, png_bytes_map)
    return result