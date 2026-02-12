import React, { useEffect, useMemo, useState } from "react";
import { runOcr } from "../src/api.js";

import Hero from "./Hero.jsx";
import ModelSelect from "./ModelSelect.jsx";
import ImageOverlay from "./ImageOverlay.jsx";
import JsonViewer from "./JsonViewer.jsx";

function safeNum(n) {
  return Number.isFinite(n) ? n : 0;
}

function computeMetrics(result) {
  const lines = Array.isArray(result?.lines) ? result.lines : [];
  const text = typeof result?.text === "string" ? result.text : "";

  // support BOTH latency_ms and backend_latency_ms
  const latency =
    result?.latency_ms ??
    result?.backend_latency_ms ??
    result?.latency ??
    0;

  const avgConf =
    lines.length === 0
      ? 0
      : lines.reduce((a, l) => a + safeNum(l?.score), 0) / lines.length;

  return {
    latency: safeNum(latency),
    numLines: lines.length,
    numChars: text.length,
    avgConf,
  };
}

export default function OcrPlayground() {
  const [selectedModel, setSelectedModel] = useState("easyocr");
  const [file, setFile] = useState(null);

  const [previewUrl, setPreviewUrl] = useState("");

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Create preview URL for image/pdf panel
  useEffect(() => {
    if (!file) {
      setPreviewUrl("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const metrics = useMemo(() => computeMetrics(result), [result]);

  async function onRun() {
    setError("");

    if (!file) {
      setError("Please choose an image or PDF first.");
      return;
    }

    try {
      setLoading(true);
      const data = await runOcr(selectedModel, file);
      setResult(data);
    } catch (e) {
      setError(typeof e?.message === "string" ? e.message : "Failed to run OCR.");
    } finally {
      setLoading(false);
    }
  }

  function downloadJson() {
    if (!result) return;

    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;

    const model = result?.model || "ocr";
    const name = result?.filename || "result";
    a.download = `${model}_${name}.json`;

    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="page">
      {/* HERO */}
      <Hero onRun={onRun} />

      {/* TWO BOXES */}
      <section className="showcase">
        {/* LEFT: INPUT */}
        <div className="big-box">
          <div className="big-box-head">
            <span className="muted-small"></span>
          </div>

          <div className="big-box-controls">
            <label className="choose-file">
              <input
                type="file"
                accept="image/*,application/pdf"
                onChange={(e) => {
                  const f = e.target.files?.[0] || null;
                  setFile(f);
                  setResult(null);
                  setError("");
                }}
              />
              <span>{file ? "Change File" : "Choose File"}</span>
            </label>

            <div className="model-wrap">
              <ModelSelect value={selectedModel} onChange={setSelectedModel} />
            </div>
          </div>

          {/* PREVIEW AREA (IMAGE OR PDF) */}
          <div className="preview-area">
            {file ? (
              <div className="preview-stage">
                <ImageOverlay
                  fileUrl={previewUrl}
                  mimeType={file?.type}
                  ocrResult={result}
                />
              </div>
            ) : (
              <div className="preview-empty">
                <div className="preview-empty-title">No image selected</div>
                <div className="muted-small"></div>
              </div>
            )}
          </div>

          {error ? <div className="error-banner">{error}</div> : null}

          <div className="bottom-note">
            Selected model: <span className="accent">{selectedModel}</span>
          </div>
        </div>

        {/* RIGHT: OUTPUT */}
        <div className="big-box">
          <div className="big-box-head">
            <h3>Benchmark Output</h3>
            <span className="muted-small"></span>
          </div>

          {!result ? (
            <div className="output-empty">
              <div className="preview-empty-title">No output yet</div>
              <div className="muted-small">
                Click <span className="accent">Run Benchmark</span> to get results.
              </div>
            </div>
          ) : (
            <div className="output-grid">
              <div className="output-card">
                <div className="output-card-title">Extracted Text</div>
                <pre className="output-pre">{result.text || ""}</pre>
              </div>

              <div className="output-card">
                <div className="output-card-title">JSON Output</div>
                <div className="json-wrap">
                  <JsonViewer data={result} />
                </div>
              </div>

              <div className="metrics-row">
                <div className="metric-pill">
                  latency{" "}
                  <span className="accent">{metrics.latency.toFixed(1)}ms</span>
                </div>
                <div className="metric-pill">
                  lines <span className="accent">{metrics.numLines}</span>
                </div>
                <div className="metric-pill">
                  chars <span className="accent">{metrics.numChars}</span>
                </div>
                <div className="metric-pill">
                  avg conf{" "}
                  <span className="accent">
                    {(metrics.avgConf * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="metrics-spacer" />

              <button className="download-btn" onClick={downloadJson}>
                Download JSON
              </button>
            </div>
          )}

          {loading ? (
            <div className="loadingPill" role="status" aria-live="polite">
              <span className="loadingSpinner" aria-hidden="true" />
              <span className="loadingText">Processing</span>
              <span className="loadingDots" aria-hidden="true">
                <i>.</i>
                <i>.</i>
                <i>.</i>
              </span>
              <span className="loadingShimmer" aria-hidden="true" />
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
