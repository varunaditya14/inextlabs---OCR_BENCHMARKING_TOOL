from enum import Enum
from typing import Any, Dict
import time

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.dummy import DummyAdapter
from app.adapters.easyocr_adapter import EasyOCRAdapter
from app.adapters.paddleocr_adapter import PaddleOCRAdapter

class ModelName(str, Enum):
    dummy = "dummy"
    easyocr = "easyocr"
    paddleocr = "paddleocr"

ADAPTERS = {
    ModelName.dummy: DummyAdapter(),
    ModelName.easyocr: EasyOCRAdapter(),
    ModelName.paddleocr: PaddleOCRAdapter(),
}


def _to_jsonable(x: Any) -> Any:
    """
    Convert numpy / non-JSON types into JSON-serializable python types.
    """
    # numpy scalar like np.int32, np.float32
    if hasattr(x, "item") and callable(getattr(x, "item")):
        try:
            return x.item()
        except Exception:
            pass

    # dict
    if isinstance(x, dict):
        return {str(k): _to_jsonable(v) for k, v in x.items()}

    # list/tuple
    if isinstance(x, (list, tuple)):
        return [_to_jsonable(v) for v in x]

    return x


app = FastAPI(title="OCR Benchmark API", version="0.1.0")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"msg": "OCR Benchmark API running. Open /docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/models")
def list_models():
    return {"models": [m.value for m in ModelName]}


@app.post("/run-ocr")
async def run_ocr(
    model: ModelName = Form(...),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    try:
        file_bytes = await file.read()

        adapter = ADAPTERS.get(model)
        if adapter is None:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

        t0 = time.perf_counter()
        result = adapter.run(filename=file.filename, file_bytes=file_bytes)
        t1 = time.perf_counter()

        result = _to_jsonable(result)
        result["latency_ms"] = round((t1 - t0) * 1000.0, 2)
        result["model"] = model.value
        result["filename"] = file.filename

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {repr(e)}")
