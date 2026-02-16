# ocr-benchmark/backend/app/billing.py

from __future__ import annotations
from typing import Any, Dict, Optional
import os

CPU_PER_HOUR_USD = float(os.getenv("CPU_PER_HOUR_USD", "0.05"))

def _to_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except Exception:
        return None

def estimate_cost_time_usd(latency_ms: Optional[float], cpu_per_hour_usd: float) -> Optional[float]:
    lm = _to_float(latency_ms)
    if lm is None:
        return None
    seconds = lm / 1000.0
    return (seconds / 3600.0) * float(cpu_per_hour_usd)

# Token pricing via env (so you can tune without code edits)
# If you don’t know real prices yet, keep 0.0 and it will fall back to time-based estimate.
def _env_price(name: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

TOKEN_PRICING_USD_PER_TOKEN: Dict[str, Dict[str, float]] = {
    # Existing placeholders you had:
    "mistral": {"in": _env_price("MISTRAL_USD_PER_INPUT_TOKEN", 0.0), "out": _env_price("MISTRAL_USD_PER_OUTPUT_TOKEN", 0.0)},
    "glm-ocr": {"in": _env_price("GLM_USD_PER_INPUT_TOKEN", 0.0), "out": _env_price("GLM_USD_PER_OUTPUT_TOKEN", 0.0)},
    "gemini3": {"in": _env_price("GEMINI3_USD_PER_INPUT_TOKEN", 0.0), "out": _env_price("GEMINI3_USD_PER_OUTPUT_TOKEN", 0.0)},
    "gemini3pro": {"in": _env_price("GEMINI3PRO_USD_PER_INPUT_TOKEN", 0.0), "out": _env_price("GEMINI3PRO_USD_PER_OUTPUT_TOKEN", 0.0)},

    # ✅ GPT-5.2 (Azure/OpenAI) – set these env vars if you know rates:
    # GPT52_USD_PER_INPUT_TOKEN and GPT52_USD_PER_OUTPUT_TOKEN
    "gpt-5.2": {"in": _env_price("GPT52_USD_PER_INPUT_TOKEN", 0.0), "out": _env_price("GPT52_USD_PER_OUTPUT_TOKEN", 0.0)},
}

def compute_cost_from_tokens(
    model: str,
    input_tokens: Optional[float],
    output_tokens: Optional[float],
) -> Optional[float]:
    pricing = TOKEN_PRICING_USD_PER_TOKEN.get(model)
    if not pricing:
        return None

    it = _to_float(input_tokens) or 0.0
    ot = _to_float(output_tokens) or 0.0

    # if both prices are zero, treat as "unknown pricing"
    if float(pricing.get("in", 0.0)) == 0.0 and float(pricing.get("out", 0.0)) == 0.0:
        return None

    return it * float(pricing.get("in", 0.0)) + ot * float(pricing.get("out", 0.0))

def build_billing(
    model: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    file_size_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Unified billing for ALL models (local + api).
      - If adapter already returns billing -> keep it
      - If token usage exists AND pricing table exists -> token cost
      - Else -> time-based estimated cost using backend_latency_ms / latency_ms
    """
    payload = payload or {}

    if isinstance(payload.get("billing"), dict):
        return payload["billing"]

    if not model:
        model = payload.get("model") or "unknown"

    meta = payload.get("meta") or {}
    usage = payload.get("usage") or {}

    latency_ms = (
        payload.get("latency_ms")
        or payload.get("backend_latency_ms")
        or meta.get("latency_ms")
    )

    input_tokens = (
        meta.get("input_tokens")
        or usage.get("input_tokens")
        or usage.get("prompt_tokens")
    )
    output_tokens = (
        meta.get("output_tokens")
        or usage.get("output_tokens")
        or usage.get("completion_tokens")
    )

    # Token-based (only if pricing exists for that model)
    token_cost = compute_cost_from_tokens(model, input_tokens, output_tokens)
    if token_cost is not None:
        return {
            "type": "api_actual_tokens",
            "basis": "tokens",
            "currency": "USD",
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(token_cost, 6),
        }

    # Fallback: time-based estimate (works for local + api)
    est = estimate_cost_time_usd(latency_ms, CPU_PER_HOUR_USD)
    return {
        "type": "estimated_time",
        "basis": "latency_ms",
        "currency": "USD",
        "model": model,
        "rate_usd_per_hour": CPU_PER_HOUR_USD,
        "cost_usd": round(est, 6) if est is not None else None,
        "file_size_bytes": file_size_bytes,
        "note": "Estimated compute cost based on runtime (not provider billing).",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
