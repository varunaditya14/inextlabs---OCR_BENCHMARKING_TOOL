// frontend/components/OcrPlayground.jsx

import { useEffect, useMemo, useState } from "react";
import { fetchModels, runOcr, downloadJson } from "../src/api.js";
import ImageOverlay from "./ImageOverlay.jsx";
import JsonViewer from "./JsonViewer.jsx";

export default function OcrPlayground() {
  const [models, setModels] = useState([]);
  const [model, setModel] = useState("");
  const [file, setFile] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  // Load models on page load
 useEffect(() => {
  (async () => {
    try {
      setError("");
      const list = await fetchModels();
      console.log("Models from backend:", list);

      const arr = Array.isArray(list) ? list : [];
      setModels(arr);
      setModel(arr[0] || "");
    } catch (e) {
      console.log("models fetch error:", e);
      setError(e.message || "Failed to load models");
      setModels([]); // make it explicit
    }   
  })();
}, []);


  const lines = useMemo(() => result?.lines || [], [result]);

  const metrics = useMemo(() => {
    if (!result) return null;

    const avgConf =
      Array.isArray(result.lines) && result.lines.length
        ? result.lines.reduce((s, x) => s + (Number(x.score) || 0), 0) /
          result.lines.length
        : null;

    const textLen = (result.text || "").length;

    return {
      model: result.model,
      filename: result.filename,
      client_latency_ms: result.client_latency_ms ?? null,
      backend_latency_ms: result.latency_ms ?? null,
      num_lines: Array.isArray(result.lines) ? result.lines.length : 0,
      text_chars: textLen,
      avg_confidence: avgConf != null ? Number(avgConf.toFixed(3)) : null,
    };
  }, [result]);

  async function onRun() {
    setError("");
    setResult(null);

    if (!model) return setError("Select a model.");
    if (!file) return setError("Upload an image first.");

    setLoading(true);
    try {
      const data = await runOcr({ model, file });
      setResult(data);
    } catch (e) {
      console.log("run ocr error:", e);
      setError(e.message || "OCR failed");
    } finally {
      setLoading(false);
    }
  }

  function onDownload() {
    if (!result) return;
    const name = (result.filename || "ocr_result").replace(/\.[^/.]+$/, "");
    downloadJson(`${name}_${result.model || "model"}.json`, result);
  }

  return (
    <>
      <div className="grid">
        <div className="panel">
          <div className="panelTitle">OCR Playground</div>

          <div className="row">
            <div className="label">Model</div>
            <select
              className="select"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              <option value="">-- Select --</option>
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <div className="row">
            <div className="label">Upload</div>
            <input
              className="file"
              type="file"
              accept="image/*"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </div>

          <div className="row">
            <button className="btn" onClick={onRun} disabled={loading}>
              {loading ? "Running..." : "Run OCR"}
            </button>

            <button className="btnSecondary" onClick={onDownload} disabled={!result}>
              Download JSON
            </button>
          </div>

          {error ? <div className="error">{error}</div> : null}

          {metrics ? (
            <div className="metrics">
              <div className="panelTitle">Benchmark Metrics</div>
              <div className="metricsGrid">
                {Object.entries(metrics).map(([k, v]) => (
                  <div key={k} className="metricItem">
                    <div className="metricKey">{k}</div>
                    <div className="metricVal">{v === null ? "-" : String(v)}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {result?.text ? (
            <div className="panel" style={{ marginTop: 12 }}>
              <div className="panelTitle">Extracted Text</div>
              <pre className="textBox">{result.text}</pre>
            </div>
          ) : null}
        </div>

        <div className="panel">
          <div className="panelTitle">Image + Bounding Boxes</div>
          <ImageOverlay file={file} lines={lines} />
          {!file ? <div className="hint">Upload an image to preview boxes.</div> : null}
        </div>
      </div>

      <JsonViewer data={result} />
    </>
  );
}
