// frontend/src/api.js

export async function runOcr(model, file) {
  const form = new FormData();
  form.append("model", model);
  form.append("file", file);

  // Use frontend env if present, else default to backend on 8000
  const base = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");

  const res = await fetch(`${base}/run-ocr`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }

  return res.json();
}
