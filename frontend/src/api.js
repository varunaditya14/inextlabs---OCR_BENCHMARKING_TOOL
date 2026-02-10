// frontend/src/api.js
const API_BASE = "";

export async function fetchModels() {
  const res = await fetch(`${API_BASE}/models`);
  if (!res.ok) throw new Error(`Failed to fetch models (${res.status})`);

  const data = await res.json();

  // backend might return ["dummy","easyocr"] OR { models: [...] }
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.models)) return data.models;

  throw new Error("Invalid /models response format");
}

export async function runOcr({ model, file }) {
  const form = new FormData();
  form.append("model", model);
  form.append("file", file);

  const t0 = performance.now();
  const res = await fetch(`${API_BASE}/run-ocr`, { method: "POST", body: form });
  const t1 = performance.now();

  let data = null;
  try {
    data = await res.json();
  } catch {
    // ignore
  }

  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `OCR failed (${res.status})`;
    throw new Error(msg);
  }

  data.client_latency_ms = Math.round(t1 - t0);
  return data;
}

export function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
