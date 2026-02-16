import React, { useEffect, useMemo, useRef, useState } from "react";
import ModelSelect from "./ModelSelect";
import { fetchModels, runOcr } from "../src/api";

export default function OcrPlayground() {
  const fileInputRef = useRef(null);

  const [models, setModels] = useState([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelsError, setModelsError] = useState("");

  const [file, setFile] = useState(null);

  const [modelA, setModelA] = useState("");
  const [modelB, setModelB] = useState("");

  const [running, setRunning] = useState(false);

  const [left, setLeft] = useState({
    loading: false,
    error: "",
    text: "",
    json: null,
    meta: null,
  });

  const [right, setRight] = useState({
    loading: false,
    error: "",
    text: "",
    json: null,
    meta: null,
  });

  // ---------------------------
  // Load models
  // ---------------------------
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setModelsError("");
        setLoadingModels(true);

        const list = await fetchModels();
        if (!mounted) return;

        setModels(list || []);

        const ids = (list || []).map((m) => m.id);
        if (!modelA && ids.length) setModelA(ids[0]);
        if (!modelB && ids.length) setModelB(ids[Math.min(1, ids.length - 1)]);
      } catch (e) {
        if (!mounted) return;
        setModels([]);
        setModelsError((e?.message || "Failed to load models").toString());
      } finally {
        if (mounted) setLoadingModels(false);
      }
    })();

    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const canRun = useMemo(() => {
    return !!file && !!modelA && !!modelB && !running;
  }, [file, modelA, modelB, running]);

  function openFilePicker() {
    fileInputRef.current?.click();
  }

  function onPickFile(e) {
    const f = e.target.files?.[0];
    if (!f) return;

    setFile(f);
    setLeft({ loading: false, error: "", text: "", json: null, meta: null });
    setRight({ loading: false, error: "", text: "", json: null, meta: null });
  }

  // ---------------------------
  // Helpers (metrics)
  // ---------------------------
  function countWords(text) {
    if (!text || typeof text !== "string") return 0;
    const t = text.trim();
    if (!t) return 0;
    return t.split(/\s+/).filter(Boolean).length;
  }

  function countLines(text) {
    if (!text || typeof text !== "string") return 0;
    return text.split("\n").filter((x) => x.trim().length > 0).length;
  }

  function fmtMs(ms) {
    if (ms == null || Number.isNaN(ms)) return "—";
    return `${Math.round(ms)} ms`;
  }

  function fmtSecondsFromMs(ms) {
    if (ms == null || Number.isNaN(ms)) return "—";
    return `${(ms / 1000).toFixed(2)} s`;
  }

  function fmtNumber(n, decimals = 0) {
    if (n == null || Number.isNaN(n)) return "—";
    return Number(n).toFixed(decimals);
  }

  function fmtFileSize(bytes) {
    if (bytes == null || Number.isNaN(bytes)) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  function inputTypeFromMime(mime) {
    const m = (mime || "").toLowerCase();
    if (m.includes("pdf")) return "PDF";
    if (m.startsWith("image/")) return "IMAGE";
    return "FILE";
  }

  // Pricing table (used only if backend doesn't return cost)
  const COST_PER_1K_CHARS_USD = {
    mistral: 0.0001,
    gemini3: 0.0003,
    gemini3pro: 0.0006,
    "glm-ocr": 0.00015,
    // local defaults:
    easyocr: 0.0,
    paddleocr: 0.0,
    trocr: 0.0,
  };

  function computeCostUsd(modelId, chars) {
    const rate = COST_PER_1K_CHARS_USD[modelId] ?? 0.0;
    const c = typeof chars === "number" ? chars : 0;
    return (c / 1000) * rate;
  }

  function buildMeta({ res, text, modelId, fileObj, tClientStartMs, tClientEndMs }) {
    const backendLatencyMs =
      res?.latency_ms ?? res?.backend_latency_ms ?? res?.backendLatencyMs ?? null;

    const clientElapsedMs =
      typeof tClientStartMs === "number" && typeof tClientEndMs === "number"
        ? Math.max(0, tClientEndMs - tClientStartMs)
        : null;

    const chars = typeof text === "string" ? text.length : 0;
    const words = countWords(text);
    const lines = countLines(text);

    const latencyMs = backendLatencyMs != null ? Number(backendLatencyMs) : null;

    const processingMs = clientElapsedMs != null ? Number(clientElapsedMs) : latencyMs;

    const charsPerSec = processingMs && processingMs > 0 ? chars / (processingMs / 1000) : null;

    const wordsPerSec = processingMs && processingMs > 0 ? words / (processingMs / 1000) : null;

    const avgCharsPerLine = lines > 0 ? chars / lines : null;

    const mime = res?.mime_type ?? fileObj?.type ?? "";
    const fileSize = fileObj?.size ?? null;

    // cost: prefer backend if it sends it, else compute
    const backendCost = res?.cost_usd ?? res?.billing?.cost_usd ?? res?.billing?.cost ?? null;

    const costUsd = backendCost != null ? Number(backendCost) : computeCostUsd(modelId, chars);

    const costPer1kChars =
      chars > 0 ? costUsd / (chars / 1000) : COST_PER_1K_CHARS_USD[modelId] ?? 0.0;

    // tokens: keep in meta if present, but UI request is to REMOVE token tiles
    const usage = res?.usage || {};
    const inputTokens = usage?.input_tokens ?? usage?.inputTokens ?? null;
    const outputTokens = usage?.output_tokens ?? usage?.outputTokens ?? null;

    return {
      model: res?.model ?? modelId,
      provider: res?.provider ?? (res?.model ?? modelId),

      latency_ms: latencyMs,
      processing_ms: processingMs,

      chars,
      words,
      lines,

      chars_per_sec: charsPerSec,
      words_per_sec: wordsPerSec,
      avg_chars_per_line: avgCharsPerLine,

      input_type: inputTypeFromMime(mime),
      file_size: fileSize,

      cost_usd: costUsd,
      cost_per_1k_chars: costPer1kChars,

      // keep raw tokens in meta if available (not displayed)
      input_tokens: inputTokens,
      output_tokens: outputTokens,
    };
  }

  // ---------------------------
  // Run benchmark
  // ---------------------------
  async function runBenchmark() {
    if (!file || !modelA || !modelB) return;

    setRunning(true);
    setLeft((p) => ({ ...p, loading: true, error: "" }));
    setRight((p) => ({ ...p, loading: true, error: "" }));

    const startLeft = performance.now();
    const taskLeft = runOcr(modelA, file).then(
      (res) => ({ side: "left", ok: true, res, end: performance.now(), start: startLeft }),
      (err) => ({ side: "left", ok: false, err })
    );

    const startRight = performance.now();
    const taskRight = runOcr(modelB, file).then(
      (res) => ({ side: "right", ok: true, res, end: performance.now(), start: startRight }),
      (err) => ({ side: "right", ok: false, err })
    );

    const results = await Promise.all([taskLeft, taskRight]);

    for (const r of results) {
      if (r.side === "left") {
        if (r.ok) {
          const text = r.res?.text ?? r.res?.result?.text ?? "";
          setLeft({
            loading: false,
            error: "",
            text,
            json: r.res ?? null,
            meta: buildMeta({
              res: r.res,
              text,
              modelId: modelA,
              fileObj: file,
              tClientStartMs: r.start,
              tClientEndMs: r.end,
            }),
          });
        } else {
          setLeft((p) => ({
            ...p,
            loading: false,
            error: (r.err?.message || "MODEL A failed").toString(),
          }));
        }
      } else {
        if (r.ok) {
          const text = r.res?.text ?? r.res?.result?.text ?? "";
          setRight({
            loading: false,
            error: "",
            text,
            json: r.res ?? null,
            meta: buildMeta({
              res: r.res,
              text,
              modelId: modelB,
              fileObj: file,
              tClientStartMs: r.start,
              tClientEndMs: r.end,
            }),
          });
        } else {
          setRight((p) => ({
            ...p,
            loading: false,
            error: (r.err?.message || "MODEL B failed").toString(),
          }));
        }
      }
    }

    setRunning(false);
  }

  function downloadJson(side) {
    const payload = side === "left" ? left.json : right.json;
    if (!payload) return;

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `${side === "left" ? "model_a" : "model_b"}_ocr_output.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const uploadStateClass = running ? "isRunning" : file ? "hasFile" : "";

  // ---------------------------
  // Metric UI blocks
  // ---------------------------
  function MetricTile({ label, value }) {
    return (
      <div className="metricCard">
        <div className="metricLabel">{label}</div>
        <div className="metricValue">{value}</div>
      </div>
    );
  }

  // ✅ UI-only: now uses CSS class for nicer section title appearance
  function MetricGroupTitle({ title }) {
    return <div className="metricsSectionTitle">{title}</div>;
  }

  // ✅ UI-only: section grouping wrappers to avoid “clustered” look
  function MetricsBox({ title, meta }) {
    return (
      <div className="outputShell" style={{ marginTop: 18 }}>
        <div className="outputHeader">
          <span className="outputTab">{title}</span>
        </div>

        <div style={{ padding: 14, background: "#fff" }}>
          <div className="metricSectionBlock">
            <MetricGroupTitle title="Performance" />
            <div className="metricsRow" style={{ gridTemplateColumns: "repeat(2, 1fr)", marginTop: 0 }}>
              <MetricTile
                label="PROCESSING TIME"
                value={meta?.processing_ms != null ? fmtSecondsFromMs(meta.processing_ms) : "—"}
              />
              <MetricTile label="LATENCY" value={meta?.latency_ms != null ? fmtMs(meta.latency_ms) : "—"} />
              <MetricTile
                label="CHARS/SEC"
                value={meta?.chars_per_sec != null ? fmtNumber(meta.chars_per_sec, 0) : "—"}
              />
              <MetricTile
                label="WORDS/SEC"
                value={meta?.words_per_sec != null ? fmtNumber(meta.words_per_sec, 0) : "—"}
              />
            </div>
          </div>

          <div className="metricSectionBlock">
            <MetricGroupTitle title="Coverage" />
            <div className="metricsRow" style={{ gridTemplateColumns: "repeat(2, 1fr)", marginTop: 0 }}>
              <MetricTile label="CHARS" value={meta?.chars ?? "—"} />
              <MetricTile label="WORDS" value={meta?.words ?? "—"} />
              <MetricTile label="LINES" value={meta?.lines ?? "—"} />
              <MetricTile
                label="AVG CHARS/LINE"
                value={meta?.avg_chars_per_line != null ? fmtNumber(meta.avg_chars_per_line, 1) : "—"}
              />
            </div>
          </div>

          <div className="metricSectionBlock">
            <MetricGroupTitle title="Run Info" />
            <div className="metricsRow" style={{ gridTemplateColumns: "repeat(2, 1fr)", marginTop: 0 }}>
              <MetricTile label="INPUT TYPE" value={meta?.input_type ?? "—"} />
              <MetricTile label="FILE SIZE" value={fmtFileSize(meta?.file_size)} />
              <MetricTile label="MODEL" value={meta?.model ?? "—"} />
              <MetricTile label="PROVIDER" value={meta?.provider ?? "—"} />
            </div>
          </div>

          <div className="metricSectionBlock">
            <MetricGroupTitle title="Cost" />
            <div className="metricsRow" style={{ gridTemplateColumns: "repeat(2, 1fr)", marginTop: 0 }}>
              <MetricTile
                label="COST (USD)"
                value={meta?.cost_usd != null ? `$${Number(meta.cost_usd).toFixed(6)}` : "—"}
              />

              <MetricTile
                label="COST / 1K CHARS"
                value={meta?.cost_per_1k_chars != null ? `$${Number(meta.cost_per_1k_chars).toFixed(4)}` : "—"}
              />

              {/* ✅ REMOVED (as you asked)
                  - INPUT TOKENS
                  - OUTPUT TOKENS
              */}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------
  // UI
  // ---------------------------
  return (
    <div className="benchPage">
      <div className="benchContainer">
        <input
          ref={fileInputRef}
          className="hiddenInput"
          type="file"
          accept="image/*,application/pdf"
          onChange={onPickFile}
        />

        <header className="heroHeader">
          <div className="heroTitle">OCR BENCHMARKING TOOL</div>
          <div className="heroTagline">Upload. Compare. models side-by-side. Export clean outputs.</div>
        </header>

        {modelsError ? <div className="miniBannerError">{modelsError}</div> : null}

        <div className="benchTopBar">
          <button className="runBtn" onClick={runBenchmark} disabled={!canRun}>
            {running ? "RUNNING..." : "RUN BENCHMARK"}
          </button>
        </div>

        <div className="benchGrid">
          {/* LEFT CARD */}
          <section className="benchCard">
            <div className="benchCard__top">
              <div className="benchTitle">
                <div className="benchTitle__main">MODEL A</div>
              </div>

              <div className="benchTopRight">
                <ModelSelect
                  label=""
                  value={modelA}
                  onChange={setModelA}
                  options={models}
                  disabled={loadingModels || running}
                />
              </div>
            </div>

            <div className="benchDivider" />

            <div className="benchBody">
              <div className="outputShell">
                <div className="outputHeader">
                  <span className="outputTab">EXTRACTED TEXT</span>
                  <button className="ghostBtn" onClick={() => downloadJson("left")} disabled={!left.json}>
                    Download JSON
                  </button>
                </div>

                <div className="outputArea">
                  {left.loading ? (
                    <div className="stateText">Processing…</div>
                  ) : left.error ? (
                    <div className="stateError">{left.error}</div>
                  ) : left.text ? (
                    <pre className="monoPre">{left.text}</pre>
                  ) : (
                    <div className="stateText">Upload a file and run benchmark.</div>
                  )}
                </div>
              </div>

              <div className="outputShell">
                <div className="outputHeader">
                  <span className="outputTab">RAW JSON</span>
                </div>

                <div className="outputArea">
                  {left.loading ? (
                    <div className="stateText">Waiting…</div>
                  ) : left.json ? (
                    <pre className="monoPre">{JSON.stringify(left.json, null, 2)}</pre>
                  ) : (
                    <div className="stateText">JSON will appear here.</div>
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* CENTER UPLOAD */}
          <div className="benchCenter">
            <button
              className={`uploadArrow ${uploadStateClass}`}
              onClick={openFilePicker}
              title={file ? `Selected: ${file.name}` : "Upload file"}
              aria-label="Upload file"
            >
              <span className="uploadRing" aria-hidden="true" />
              <svg className="uploadIcon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 3v10" stroke="white" strokeWidth="2.4" strokeLinecap="round" />
                <path
                  d="M8.5 6.5 12 3l3.5 3.5"
                  stroke="white"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M4 14.5v4A2.5 2.5 0 0 0 6.5 21h11A2.5 2.5 0 0 0 20 18.5v-4"
                  stroke="white"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>

          {/* RIGHT CARD */}
          <section className="benchCard">
            <div className="benchCard__top">
              <div className="benchTitle">
                <div className="benchTitle__main">MODEL B</div>
              </div>

              <div className="benchTopRight">
                <ModelSelect
                  label=""
                  value={modelB}
                  onChange={setModelB}
                  options={models}
                  disabled={loadingModels || running}
                />
              </div>
            </div>

            <div className="benchDivider" />

            <div className="benchBody">
              <div className="outputShell">
                <div className="outputHeader">
                  <span className="outputTab">EXTRACTED TEXT</span>
                  <button className="ghostBtn" onClick={() => downloadJson("right")} disabled={!right.json}>
                    Download JSON
                  </button>
                </div>

                <div className="outputArea">
                  {right.loading ? (
                    <div className="stateText">Processing…</div>
                  ) : right.error ? (
                    <div className="stateError">{right.error}</div>
                  ) : right.text ? (
                    <pre className="monoPre">{right.text}</pre>
                  ) : (
                    <div className="stateText">Upload a file and run benchmark.</div>
                  )}
                </div>
              </div>

              <div className="outputShell">
                <div className="outputHeader">
                  <span className="outputTab">RAW JSON</span>
                </div>

                <div className="outputArea">
                  {right.loading ? (
                    <div className="stateText">Waiting…</div>
                  ) : right.json ? (
                    <pre className="monoPre">{JSON.stringify(right.json, null, 2)}</pre>
                  ) : (
                    <div className="stateText">JSON will appear here.</div>
                  )}
                </div>
              </div>
            </div>
          </section>
        </div>

        {/* ✅ Separate metrics boxes under each side */}
        <div className="benchGrid" style={{ marginTop: 18 }}>
          <div>
            <MetricsBox title="MODEL A METRICS" meta={left.meta} />
          </div>

          <div />

          <div>
            <MetricsBox title="MODEL B METRICS" meta={right.meta} />
          </div>
        </div>
      </div>
    </div>
  );
}
