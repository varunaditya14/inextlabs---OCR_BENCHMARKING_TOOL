// frontend/components/OcrCompare.jsx
import React, { useMemo, useState } from "react";
import ModelMetrics from "./ModelMetrics";

const BRAND = "#f05742";

function prettyJson(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

async function runOcrRequest({ file, model }) {
  const form = new FormData();
  form.append("file", file);
  form.append("model", model);

  // If you already use a proxy (vite.config.js) to /api, switch URL accordingly.
  // Most of your project earlier used backend at http://127.0.0.1:8000/run-ocr
  const res = await fetch("http://127.0.0.1:8000/run-ocr", {
    method: "POST",
    body: form,
  });

  let data;
  try {
    data = await res.json();
  } catch {
    const text = await res.text();
    throw new Error(`Backend returned non-JSON: ${text.slice(0, 200)}`);
  }

  if (!res.ok) {
    const detail = data?.detail ?? "Unknown error";
    throw new Error(typeof detail === "string" ? detail : prettyJson(detail));
  }

  return data;
}

export default function OcrCompare() {
  // Keep these in sync with backend keys used in your adapters registry.
  const modelOptions = useMemo(
    () => [
      { label: "EasyOCR", value: "easyocr" },
      { label: "PaddleOCR", value: "paddleocr" },
      { label: "Mistral OCR", value: "mistral" },
      { label: "GLM OCR", value: "glm-ocr" },
      { label: "Gemini 3", value: "gemini3" },
      { label: "TrOCR", value: "trocr" },
    ],
    []
  );

  const [file, setFile] = useState(null);

  const [modelA, setModelA] = useState(modelOptions[0]?.value || "easyocr");
  const [modelB, setModelB] = useState(modelOptions[2]?.value || "mistral");

  const [loading, setLoading] = useState(false);

  const [outA, setOutA] = useState(null);
  const [outB, setOutB] = useState(null);

  const [errA, setErrA] = useState("");
  const [errB, setErrB] = useState("");

  const canRun = !!file && !loading;

  const onPickFile = (e) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setOutA(null);
    setOutB(null);
    setErrA("");
    setErrB("");
  };

  const runBoth = async () => {
    if (!file) return;

    setLoading(true);
    setErrA("");
    setErrB("");

    // Run both in parallel; each side handles its own error.
    const [a, b] = await Promise.allSettled([
      runOcrRequest({ file, model: modelA }),
      runOcrRequest({ file, model: modelB }),
    ]);

    if (a.status === "fulfilled") setOutA(a.value);
    else setErrA(a.reason?.message || "Model A failed");

    if (b.status === "fulfilled") setOutB(b.value);
    else setErrB(b.reason?.message || "Model B failed");

    setLoading(false);
  };

  return (
    <div className="cmp-page">
      <header className="cmp-header">
        <div>
          <div className="cmp-title">OCR Benchmarking Tool</div>
          <div className="cmp-subtitle">
            Compare two OCR engines side-by-side on the same file.
          </div>
        </div>

        <button
          className="cmp-run"
          onClick={runBoth}
          disabled={!canRun}
          title={!file ? "Upload a file first" : "Run both"}
          style={{ background: BRAND }}
        >
          {loading ? "Running..." : "Run Both"}
        </button>
      </header>

      <div className="cmp-uploadRow">
        <label
          className="cmp-uploadBtn"
          style={{ borderColor: BRAND, color: BRAND }}
        >
          <input
            className="cmp-fileInput"
            type="file"
            accept=".png,.jpg,.jpeg,.webp,.pdf"
            onChange={onPickFile}
          />
          Choose File
        </label>

        <div className="cmp-fileName">
          {file ? file.name : "No file selected (image or PDF)"}
        </div>
      </div>

      <div className="cmp-grid">
        {/* LEFT (A) */}
        <section className="cmp-card">
          <div className="cmp-cardHead">
            <div className="cmp-cardTitle">A</div>

            <div className="cmp-selectWrap">
              <div className="cmp-label">Model</div>
              <select
                className="cmp-select"
                value={modelA}
                onChange={(e) => setModelA(e.target.value)}
                disabled={loading}
              >
                {modelOptions.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {errA ? (
            <div className="cmp-error">
              <div className="cmp-errorTitle">Error</div>
              <div className="cmp-errorMsg">{errA}</div>
            </div>
          ) : null}

          <div className="cmp-block">
            <div className="cmp-blockTitle">Extracted Text</div>
            <pre className="cmp-pre">{outA?.text || "No output yet."}</pre>
          </div>

          <div className="cmp-block">
            <div className="cmp-blockTitle">JSON Output</div>
            <pre className="cmp-pre">{outA ? prettyJson(outA) : "-"}</pre>
          </div>

          {/* ✅ NEW: Model A Metrics Box (below Model A card content) */}
          <ModelMetrics
            title="MODEL A METRICS"
            modelName={modelA}
            result={outA}
            otherText={outB?.text || ""}
          />
        </section>

        {/* RIGHT (B) */}
        <section className="cmp-card">
          <div className="cmp-cardHead">
            <div className="cmp-cardTitle">B</div>

            <div className="cmp-selectWrap">
              <div className="cmp-label">Model</div>
              <select
                className="cmp-select"
                value={modelB}
                onChange={(e) => setModelB(e.target.value)}
                disabled={loading}
              >
                {modelOptions.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {errB ? (
            <div className="cmp-error">
              <div className="cmp-errorTitle">Error</div>
              <div className="cmp-errorMsg">{errB}</div>
            </div>
          ) : null}

          <div className="cmp-block">
            <div className="cmp-blockTitle">Extracted Text</div>
            <pre className="cmp-pre">{outB?.text || "No output yet."}</pre>
          </div>

          <div className="cmp-block">
            <div className="cmp-blockTitle">JSON Output</div>
            <pre className="cmp-pre">{outB ? prettyJson(outB) : "-"}</pre>
          </div>

          {/* ✅ NEW: Model B Metrics Box (below Model B card content) */}
          <ModelMetrics
            title="MODEL B METRICS"
            modelName={modelB}
            result={outB}
            otherText={outA?.text || ""}
          />
        </section>
      </div>
    </div>
  );
}
