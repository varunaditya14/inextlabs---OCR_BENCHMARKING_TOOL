export async function runOcr(model, file) {
  const form = new FormData();
  form.append("model", model);
  form.append("file", file);

  const res = await fetch("http://127.0.0.1:8000/run-ocr", {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }

  return res.json();
}
