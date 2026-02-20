// frontend/src/api.js

const BACKEND_URL =
  (import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function safeJson(res) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function normalizeModels(payload) {
  const list =
    (Array.isArray(payload) && payload) ||
    payload?.models ||
    payload?.data ||
    payload?.items ||
    [];

  if (!Array.isArray(list)) return [];

  return list
    .map((x) => {
      if (typeof x === "string") return { id: x, label: x };
      const id = x?.id ?? x?.value ?? x?.name ?? x?.model ?? "";
      const label = x?.label ?? x?.name ?? x?.id ?? x?.value ?? x?.model ?? "";
      if (!id) return null;
      return { id, label };
    })
    .filter(Boolean);
}

async function fetchFirstWorking(pathList) {
  let lastErr = null;

  for (const path of pathList) {
    try {
      const url = `${BACKEND_URL}${path}`;
      const res = await fetch(url, { method: "GET" });

      if (!res.ok) {
        lastErr = new Error(`GET ${path} -> HTTP ${res.status}`);
        continue;
      }

      const data = await safeJson(res);
      const models = normalizeModels(data);
      return models;
    } catch (e) {
      lastErr = e;
    }
  }

  const msg =
    lastErr?.message?.includes("Failed to fetch") ||
    lastErr?.message?.includes("ERR_CONNECTION_REFUSED")
      ? `Backend not reachable at ${BACKEND_URL}. Is FastAPI running on port 8000?`
      : lastErr?.message || "Unable to load models from backend";

  throw new Error(msg);
}

export async function fetchModels() {
  return await fetchFirstWorking(["/models", "/ocr/models", "/api/models", "/v1/models"]);
}

export async function runOcr(modelId, file) {
  const fd = new FormData();
  fd.append("model", modelId);
  fd.append("file", file);

  const res = await fetch(`${BACKEND_URL}/run-ocr`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const data = await safeJson(res);
    const msg = data?.detail || data?.message || data?.error || `HTTP ${res.status}`;
    throw new Error(msg);
  }

  return await res.json();
}

/**
 * ✅ NEW: Run ALL models in ONE backend call.
 * Backend endpoint must exist: POST /run-benchmark
 * Response shape:
 *   { filename, mime_type, results: { [modelId]: resultOrErrorObj } }
 */
export async function runBenchmark(file) {
  const fd = new FormData();
  fd.append("file", file);

  const res = await fetch(`${BACKEND_URL}/run-benchmark`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const data = await safeJson(res);
    const msg = data?.detail || data?.message || data?.error || `HTTP ${res.status}`;
    throw new Error(msg);
  }

  return await res.json();
}