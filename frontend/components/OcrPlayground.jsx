// components/OcrPlayground.jsx
import React, { useEffect, useMemo, useState } from "react";
import { fetchModels, runBenchmark } from "../src/api";
import ExtractedTextBox from "./ExtractedTextBox";
import CompareModal from "./CompareModal";

function wordCount(text) {
  if (!text) return 0;
  return String(text).trim().split(/\s+/).filter(Boolean).length;
}

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** ✅ Metrics shimmer (lazy loading) */
function MetricsSkeleton() {
  const line = (w, h = 12, d = 0) => (
    <div
      style={{
        width: w,
        height: h,
        borderRadius: 999,
        position: "relative",
        overflow: "hidden",
        background: "rgba(240,87,66,0.10)",
        border: "1px solid rgba(240,87,66,0.10)",
        boxShadow: "0 1px 0 rgba(16,24,40,0.03) inset",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(90deg, rgba(240,87,66,0.04), rgba(240,87,66,0.22), rgba(240,87,66,0.04))",
          backgroundSize: "220% 100%",
          animation: "wbShimmer 1.15s ease-in-out infinite",
          animationDelay: `${d}s`,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: -10,
          bottom: -10,
          width: 46,
          background:
            "linear-gradient(90deg, rgba(240,87,66,0), rgba(240,87,66,0.25), rgba(240,87,66,0))",
          animation: "wbScan 2.2s ease-in-out infinite",
          animationDelay: `${d * 0.6}s`,
          opacity: 0.9,
        }}
      />
    </div>
  );

  return (
    <div style={{ padding: "2px 0" }}>
      <style>
        {`
          @keyframes wbShimmer {
            0% { background-position: 210% 0; opacity: 0.75; }
            50% { opacity: 1; }
            100% { background-position: -210% 0; opacity: 0.75; }
          }
          @keyframes wbScan {
            0% { transform: translateX(-60px); opacity: 0.2; }
            45% { opacity: 0.85; }
            100% { transform: translateX(520px); opacity: 0.2; }
          }
        `}
      </style>

      <div style={{ display: "grid", gap: 8 }}>
        {line("42%", 10, 0)}
        {line("68%", 18, 0.08)}
      </div>
    </div>
  );
}

/** ✅ Preview modal */
function PreviewModal({
  open,
  onClose,
  file,
  isPdf,
  extractedText,
  rawJson,
  models,
  selectedModel,
  onSelectModel,
}) {
  const [objectUrl, setObjectUrl] = useState("");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [expandedPane, setExpandedPane] = useState(null);

  useEffect(() => {
    if (!open || !file) return;
    const url = URL.createObjectURL(file);
    setObjectUrl(url);
    return () => {
      URL.revokeObjectURL(url);
      setObjectUrl("");
    };
  }, [open, file]);

  useEffect(() => {
    if (!open) {
      setIsFullscreen(false);
      setExpandedPane(null);
    }
  }, [open]);

  if (!open) return null;

  const headerRightStyle = {
    display: "inline-flex",
    alignItems: "center",
    gap: "10px",
  };

  const iconBtnStyle = {
    height: "34px",
    minWidth: "34px",
    padding: "0 10px",
    borderRadius: "10px",
    border: "1px solid rgba(16,24,40,0.12)",
    background: "#fff",
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    lineHeight: 1,
    fontWeight: 800,
    userSelect: "none",
  };

  const iconBtnStyleGhost = {
    ...iconBtnStyle,
    background: "rgba(240,87,66,0.05)",
    border: "1px solid rgba(240,87,66,0.18)",
  };

  const modalStyle = isFullscreen
    ? {
        width: "100vw",
        height: "100vh",
        maxWidth: "100vw",
        maxHeight: "100vh",
        borderRadius: 0,
      }
    : undefined;

  const outSplitStyle = {
    display: "grid",
    gridTemplateRows: expandedPane ? "1fr" : "1fr 1fr",
    gap: "12px",
    height: "100%",
    minHeight: 0,
    padding: "12px",
  };

  const boxStyle = {
    border: "1px solid rgba(16,24,40,0.12)",
    borderRadius: "12px",
    overflow: "hidden",
    background: "#fff",
    display: "grid",
    gridTemplateRows: "auto 1fr",
    minHeight: 0,
  };

  const titleStyle = {
    padding: "10px 12px",
    fontWeight: 700,
    borderBottom: "1px solid rgba(16,24,40,0.08)",
    background: "rgba(240,87,66,0.05)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "10px",
  };

  const smallIconBtnStyle = {
    height: "28px",
    minWidth: "28px",
    padding: "0 8px",
    borderRadius: "9px",
    border: "1px solid rgba(16,24,40,0.12)",
    background: "#fff",
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    lineHeight: 1,
    fontWeight: 900,
    userSelect: "none",
  };

  const scrollWrapStyle = {
    background: "#111827",
    overflow: "auto",
    minHeight: 0,
  };

  const preStyle = {
    margin: 0,
    padding: "10px 12px",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    fontFamily:
      'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
    fontSize: "13px",
    lineHeight: 1.5,
    color: "#e5e7eb",
  };

  const toggleExpand = (which) => {
    setExpandedPane((prev) => (prev === which ? null : which));
  };

  return (
    <div className="pvOverlay" onMouseDown={() => onClose()}>
      <div className="pvModal" style={modalStyle} onMouseDown={(e) => e.stopPropagation()}>
        <div className="pvHeader">
          <div className="pvTitle">Input &amp; Output Preview</div>

          <div style={headerRightStyle}>
            <select
              className="modelSelect2"
              value={selectedModel}
              onChange={(e) => onSelectModel?.(e.target.value)}
              disabled={!models?.length}
              style={{ height: "34px", minWidth: "180px" }}
              aria-label="Select model (preview)"
            >
              {(models || []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label || m.id}
                </option>
              ))}
            </select>

            <button
              type="button"
              style={iconBtnStyleGhost}
              onClick={() => setIsFullscreen((v) => !v)}
              aria-label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
              title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            >
              {isFullscreen ? "⤡" : "⤢"}
            </button>

            <button className="pvClose" onClick={onClose} aria-label="Close" title="Close">
              ×
            </button>
          </div>
        </div>

        <div className="pvBody">
          <div className="pvPane">
            <div className="pvPaneTitle">Input File</div>
            <div className="pvPaneInner">
              {file ? (
                isPdf ? (
                  <iframe className="pvFrame" src={objectUrl} title="PDF Preview" />
                ) : (
                  <img className="pvImg" src={objectUrl} alt="Input Preview" />
                )
              ) : (
                <div className="pvEmpty">No file</div>
              )}
            </div>
          </div>

          <div className="pvPane">
            <div className="pvPaneTitle">Output</div>

            <div style={outSplitStyle}>
              {(expandedPane === null || expandedPane === "text") && (
                <div style={boxStyle}>
                  <div style={titleStyle}>
                    <div>Extracted Text</div>
                    <button
                      type="button"
                      style={smallIconBtnStyle}
                      onClick={() => toggleExpand("text")}
                      aria-label={expandedPane === "text" ? "Collapse Extracted Text" : "Expand Extracted Text"}
                      title={expandedPane === "text" ? "Collapse" : "Expand"}
                    >
                      {expandedPane === "text" ? "⤡" : "⤢"}
                    </button>
                  </div>
                  <div style={scrollWrapStyle}>
                    <pre style={preStyle}>{extractedText || ""}</pre>
                  </div>
                </div>
              )}

              {(expandedPane === null || expandedPane === "json") && (
                <div style={boxStyle}>
                  <div style={titleStyle}>
                    <div>Raw JSON</div>
                    <button
                      type="button"
                      style={smallIconBtnStyle}
                      onClick={() => toggleExpand("json")}
                      aria-label={expandedPane === "json" ? "Collapse Raw JSON" : "Expand Raw JSON"}
                      title={expandedPane === "json" ? "Collapse" : "Expand"}
                    >
                      {expandedPane === "json" ? "⤡" : "⤢"}
                    </button>
                  </div>
                  <div style={scrollWrapStyle}>
                    <pre style={preStyle}>{JSON.stringify(rawJson || {}, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------ ✅ More Metrics (FIXED + USEFUL) ------------------------ */

const clamp01 = (x) => Math.max(0, Math.min(1, x));

function computeMoreMetrics(result) {
  const text = String(result?.text ?? "");
  const chars = text.length;

  const latencyMs =
    (typeof result?.latency_ms === "number" && result.latency_ms) ||
    (typeof result?.backend_latency_ms === "number" && result.backend_latency_ms) ||
    null;

  const seconds = latencyMs ? latencyMs / 1000 : null;
  const charsPerSec = seconds && chars ? chars / seconds : null;

  const billing = result?.billing || {};
  const costUsd = typeof billing?.cost_usd === "number" ? billing.cost_usd : null;

  // Prefer backend cost_per_1k if provided; else derive from costUsd + chars.
  const backendCostPer1k =
    typeof billing?.cost_per_1k_chars_usd === "number" ? billing.cost_per_1k_chars_usd : null;

  const derivedCostPer1k =
    backendCostPer1k != null
      ? backendCostPer1k
      : costUsd != null && chars > 0
      ? costUsd * (1000 / chars)
      : null;

  const outputKb = Math.round((new Blob([text]).size / 1024) * 10) / 10;

  // ✅ Better “noise”: weird characters (exclude common punctuation used in invoices/tables)
  // We count only characters that are NOT:
  // - letters/digits/space
  // - common invoice punctuation: . , : ; - / ( ) [ ] { } # @ & % + = * ' " _ | \n \t
  const weirdMatches = text.match(/[^a-zA-Z0-9\s\.\,\:\;\-\(\)\[\]\{\}\/\\#@&%+=\*'"_\|\t\n]/g) || [];
  const weirdPct = chars ? Math.round((weirdMatches.length / chars) * 1000) / 10 : 0;

  // Digit ratio %
  const digitMatches = text.match(/[0-9]/g) || [];
  const digitPct = chars ? Math.round((digitMatches.length / chars) * 1000) / 10 : 0;

  // Duplicate line ratio %
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter((l) => l.length > 0);
  const totalLines = lines.length;
  const uniqueLines = new Set(lines).size;
  const dupLines = totalLines ? totalLines - uniqueLines : 0;
  const dupLinePct = totalLines ? Math.round((dupLines / totalLines) * 1000) / 10 : 0;

  // ✅ Efficiency score (0–10): speed + cost + cleanliness (weird + duplication)
  // speed: saturate near 1200 chars/sec
  const speedScore = charsPerSec ? clamp01(charsPerSec / 1200) : 0;

  // cost: good if <= 0.005 per 1K; bad if >= 0.02
  const costScore =
    derivedCostPer1k != null ? clamp01((0.02 - derivedCostPer1k) / (0.02 - 0.005)) : 0.35;

  // cleanliness: weird <= 1% and duplicate lines <= 5% are good
  const weirdScore = clamp01((1.5 - weirdPct) / 1.5); // 0..1
  const dupScore = clamp01((12 - dupLinePct) / 12); // 0..1
  const cleanScore = 0.6 * weirdScore + 0.4 * dupScore;

  const efficiencyScore =
    Math.round((10 * (0.45 * speedScore + 0.35 * costScore + 0.20 * cleanScore)) * 10) / 10;

  return {
    costUsd,
    costPer1k: derivedCostPer1k,
    outputKb,
    weirdPct,
    digitPct,
    dupLinePct,
    efficiencyScore,
  };
}

function MoreMetricsModal({ open, onClose, title, result }) {
  if (!open) return null;

  const m = computeMoreMetrics(result);

  const Card = ({ label, value, sub }) => (
    <div
      style={{
        background: "#fff7f5",
        border: "1px solid rgba(16,24,40,0.10)",
        borderRadius: 16,
        padding: 14,
        boxShadow: "0 8px 22px rgba(0,0,0,0.06)",
      }}
    >
      <div style={{ fontSize: 12, letterSpacing: 0.6, opacity: 0.75, fontWeight: 800 }}>
        {String(label || "").toUpperCase()}
      </div>
      <div style={{ fontSize: 22, fontWeight: 900, marginTop: 6 }}>{value}</div>
      {sub ? (
        <div style={{ marginTop: 6, fontSize: 12, opacity: 0.75, fontWeight: 700 }}>{sub}</div>
      ) : null}
    </div>
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.35)",
        display: "grid",
        placeItems: "center",
        zIndex: 80,
        padding: 16,
      }}
    >
      <div
        style={{
          width: "min(920px, 96vw)",
          maxHeight: "88vh",
          overflow: "auto",
          background: "#fff",
          borderRadius: 20,
          border: "1px solid rgba(16,24,40,0.12)",
          boxShadow: "0 16px 40px rgba(0,0,0,0.18)",
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div
          style={{
            padding: 16,
            borderBottom: "1px solid rgba(16,24,40,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <div style={{ fontWeight: 900 }}>{title}</div>
          <button type="button" className="btnPrimary2" onClick={onClose}>
            Close
          </button>
        </div>

        <div style={{ padding: 16 }}>
          <div style={{ marginBottom: 10, fontWeight: 900, opacity: 0.85 }}>Efficiency Score</div>

          <Card
            label="Efficiency"
            value={typeof m.efficiencyScore === "number" ? `${m.efficiencyScore} / 10` : "—"}
            sub=""
          />

          <div style={{ height: 14 }} />

          <div style={{ marginBottom: 10, fontWeight: 900, opacity: 0.85 }}>Detailed Metrics</div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
              gap: 12,
            }}
          >
            <Card
              label="Cost (USD)"
              value={typeof m.costUsd === "number" ? `$${m.costUsd.toFixed(6)}` : "—"}
              sub=""
            />

            <Card
              label="Cost / 1K chars"
              value={typeof m.costPer1k === "number" ? `$${m.costPer1k.toFixed(6)}` : "—"}
              sub=""
            />

            <Card
              label="Output Size"
              value={`${m.outputKb} KB`}
              sub="How heavy the extracted text is"
            />

            <Card
              label="Weird Char %"
              value={`${m.weirdPct}%`}
              sub="Non-standard symbols"
            />

            <Card
              label="Digit %"
              value={`${m.digitPct}%`}
              sub="Helpful for invoices/receipts"
            />

            <Card
              label="Duplicate Line %"
              value={`${m.dupLinePct}%`}
              sub="Repeated lines / total lines"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------------- */

export default function OcrPlayground() {
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");

  const [file, setFile] = useState(null);
  const [executing, setExecuting] = useState(false);
  const [executed, setExecuted] = useState(false);

  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  const [resultsByModel, setResultsByModel] = useState({});

  const [isCompareOpen, setIsCompareOpen] = useState(false);
  const [compareModels, setCompareModels] = useState([]);

  const [isMoreMetricsOpen, setIsMoreMetricsOpen] = useState(false);

  useEffect(() => {
    (async () => {
      const list = await fetchModels();
      setModels(list || []);
      if (list?.length) setSelectedModel((prev) => prev || list[0].id);
    })();
  }, []);

  const fileMeta = useMemo(() => {
    if (!file) return null;
    return { name: file.name, size: file.size, type: file.type || "unknown" };
  }, [file]);

  const isPdf = useMemo(() => {
    if (!fileMeta?.name) return false;
    return (fileMeta.type || "").includes("pdf") || fileMeta.name.toLowerCase().endsWith(".pdf");
  }, [fileMeta]);

  const selectedEntry = selectedModel ? resultsByModel[selectedModel] : null;
  const selectedResult = selectedEntry?.result || null;
  const selectedError = selectedEntry?.error || null;

  const metricsLoading = executing || selectedEntry?.status === "running";

  const summaryMetrics = useMemo(() => {
    if (!selectedResult) return null;

    const latencyMs = selectedResult?.latency_ms ?? selectedResult?.backend_latency_ms ?? null;
    const text = selectedResult?.text ?? "";
    const chars = text.length;
    const words = wordCount(text);

    const linesArr =
      Array.isArray(selectedResult?.lines)
        ? selectedResult.lines
        : Array.isArray(selectedResult?.Lines)
        ? selectedResult.Lines
        : null;

    const lines = linesArr ? linesArr.length : text ? text.split(/\r?\n/).length : 0;

    const seconds = latencyMs ? latencyMs / 1000 : null;
    const charsPerSec = seconds ? Math.round(chars / seconds) : null;

    const billing = selectedResult?.billing || {};
    const costUsd = typeof billing?.cost_usd === "number" ? billing.cost_usd : null;
    const costPer1k =
      typeof billing?.cost_per_1k_chars_usd === "number" ? billing.cost_per_1k_chars_usd : null;

    return {
      latencyMs: latencyMs != null ? `${Math.round(latencyMs)} ms` : "—",
      chars: chars ? `${chars}` : "—",
      words: words ? `${words}` : "—",
      lines: lines ? `${lines}` : "—",
      charsPerSec: charsPerSec != null ? `${charsPerSec}` : "—",
      costUsd: costUsd != null ? `$${costUsd.toFixed(6)}` : "—",
      costPer1k: costPer1k != null ? `$${costPer1k.toFixed(6)}` : null,
    };
  }, [selectedResult]);

  function resetRunState() {
    setExecuted(false);
    setResultsByModel({});
  }

  function onPickFile(f) {
    setFile(f);
    resetRunState();
  }

  function removeFile() {
    setFile(null);
    resetRunState();
    setIsPreviewOpen(false);
    setIsCompareOpen(false);
    setIsMoreMetricsOpen(false);
  }

  function openCompare() {
    const allIds = (models || []).map((m) => m?.id).filter(Boolean);

    const base = [];
    if (selectedModel) base.push(selectedModel);

    for (const id of allIds) {
      if (base.length >= 2) break;
      if (!base.includes(id)) base.push(id);
    }

    setCompareModels(base.slice(0, 3));
    setIsCompareOpen(true);
  }

  async function executeAllModels() {
    if (!file || !models.length || executing) return;

    setExecuting(true);
    setExecuted(false);

    const init = {};
    models.forEach((m) => {
      init[m.id] = { status: "running", result: null, error: null };
    });
    setResultsByModel(init);

    try {
      const payload = await runBenchmark(file);
      const results = payload?.results || {};

      setResultsByModel((prev) => {
        const next = { ...prev };

        models.forEach((m) => {
          const r = results[m.id];

          if (!r) {
            next[m.id] = { status: "error", result: null, error: "No result returned" };
            return;
          }

          if (r?.error) {
            next[m.id] = { status: "error", result: null, error: String(r.error) };
            return;
          }

          next[m.id] = { status: "success", result: r, error: null };
        });

        return next;
      });

      setExecuted(true);
    } catch (e) {
      const msg = e?.message || "Benchmark failed";
      setResultsByModel((prev) => {
        const next = { ...prev };
        models.forEach((m) => {
          next[m.id] = { status: "error", result: null, error: msg };
        });
        return next;
      });
      setExecuted(false);
    } finally {
      setExecuting(false);
    }
  }

  return (
    <div className="wb2">
      <div className="wb2Grid" style={{ display: "grid", gridTemplateColumns: "1fr", gap: "24px" }}>
        {/* INPUT PANEL */}
        <section className="panel2">
          <div className="panel2Header">
            <div className="panel2Title">Input Panel</div>
          </div>

          <div className="panel2Body">
            <div className="uploadWrap">
              {!file ? (
                <label className="dropzone2">
                  <input
                    type="file"
                    accept="image/*,application/pdf"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) onPickFile(f);
                    }}
                    style={{ display: "none" }}
                  />
                  <div className="dz2Icon">
                    <div className="dz2IconDoc" />
                  </div>
                  <div className="dz2Title">Upload Image or PDF</div>
                  <div className="dz2Hint">Click to browse</div>
                </label>
              ) : (
                <div className="fileCard2">
                  <div className={`tickBadge ${executing ? "tickBadge--hide" : "tickBadge--show"}`}>
                    <svg viewBox="0 0 24 24" className="tickIcon" aria-hidden="true">
                      <path
                        d="M20 6L9 17l-5-5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>

                  <div className="filePreviewBox">
                    <div className="fileDocIcon2">
                      <svg viewBox="0 0 24 24" className="docSvg" aria-hidden="true">
                        <path
                          d="M14 2H7a3 3 0 0 0-3 3v14a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V8l-6-6z"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                        <path
                          d="M14 2v6h6"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </div>
                    <div className="fileDocLabel">{isPdf ? "PDF Document" : "Image File"}</div>
                  </div>

                  <div className="fileName2">{fileMeta?.name}</div>

                  <button className="btnRemove2" onClick={removeFile} disabled={executing}>
                    Remove File
                  </button>

                  <div className="fileReplaceHint">or drag & drop another file to replace</div>
                </div>
              )}
            </div>

            <div className={`successBar ${executed ? "successBar--show" : ""}`}>
              <div className="successBarFill" />
              <div className="successBarText">Executed — Change config or file to re-run</div>
            </div>
          </div>

          <div className="panel2Footer panel2FooterCenter">
            <button
              className={`btnExecute2 ${executed ? "btnExecute2--done" : ""}`}
              onClick={executeAllModels}
              disabled={!file || executing || !models.length}
            >
              {executing ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span>Executing</span>
                  <span className="wbDots" aria-hidden="true">
                    ...
                  </span>
                </span>
              ) : executed ? (
                "Executed"
              ) : (
                "Execute"
              )}
            </button>
          </div>
        </section>

        {/* OUTPUT PANEL */}
        <section className="panel2">
          <div className="panel2Header panel2HeaderRow">
            <div className="panel2Title">Output Panel</div>

            <div className="panel2HeaderRight">
              <select
                className="modelSelect2"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={!models.length}
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label || m.id}
                  </option>
                ))}
              </select>

              <button className="btnGhost2" type="button" disabled={!file} onClick={openCompare}>
                Compare
              </button>

              <button
                className="btnGhost2"
                type="button"
                disabled={!file}
                onClick={() => setIsPreviewOpen(true)}
              >
                Preview
              </button>

              <button
                className="btnPrimary2"
                type="button"
                disabled={!selectedResult}
                onClick={() => {
                  if (!selectedResult) return;
                  downloadJson(
                    `${selectedModel || "model"}_${fileMeta?.name || "output"}.json`,
                    selectedResult?.raw ?? selectedResult
                  );
                }}
              >
                Download JSON
              </button>
            </div>
          </div>

          <div className="panel2Body">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "16px",
                alignItems: "start",
                marginTop: "12px",
              }}
            >
              {/* LEFT */}
              <div>
                <ExtractedTextBox
                  result={selectedResult}
                  loading={selectedEntry?.status === "running" || (executing && !selectedResult)}
                />
              </div>

              {/* RIGHT */}
              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 12,
                    marginBottom: 10,
                  }}
                >
                  <div className="metricsTitle2" style={{ margin: 0 }}>
                    Key Metrics
                  </div>

                  <button
                    className="btnGhost2"
                    type="button"
                    disabled={!selectedResult}
                    onClick={() => setIsMoreMetricsOpen(true)}
                    title={!selectedResult ? "Run OCR to view more metrics" : "View more metrics"}
                  >
                    More metrics
                  </button>
                </div>

                <div className="metricsGrid2">
                  <div className="metricBox2">
                    <div className="metricLabel2">Latency</div>
                    <div className="metricValue2">
                      {metricsLoading ? <MetricsSkeleton /> : summaryMetrics?.latencyMs || "—"}
                    </div>
                  </div>

                  <div className="metricBox2">
                    <div className="metricLabel2">Chars Processed</div>
                    <div className="metricValue2">
                      {metricsLoading ? <MetricsSkeleton /> : summaryMetrics?.chars || "—"}
                    </div>
                  </div>

                  <div className="metricBox2">
                    <div className="metricLabel2">Words</div>
                    <div className="metricValue2">
                      {metricsLoading ? <MetricsSkeleton /> : summaryMetrics?.words || "—"}
                    </div>
                  </div>

                  <div className="metricBox2">
                    <div className="metricLabel2">Lines</div>
                    <div className="metricValue2">
                      {metricsLoading ? <MetricsSkeleton /> : summaryMetrics?.lines || "—"}
                    </div>
                  </div>

                  <div className="metricBox2">
                    <div className="metricLabel2">Chars / Sec</div>
                    <div className="metricValue2">
                      {metricsLoading ? <MetricsSkeleton /> : summaryMetrics?.charsPerSec || "—"}
                    </div>
                  </div>

                  <div className="metricBox2">
                    <div className="metricLabel2">Cost (USD)</div>

                    <div className="metricValue2">
                      {metricsLoading ? <MetricsSkeleton /> : summaryMetrics?.costUsd || "—"}
                    </div>

                    {!metricsLoading &&
                    summaryMetrics?.costPer1k &&
                    summaryMetrics.costPer1k !== "—" && (
                    <div className="metricSub2">Cost / 1K chars: {summaryMetrics.costPer1k}</div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <PreviewModal
              open={isPreviewOpen}
              onClose={() => setIsPreviewOpen(false)}
              file={file}
              isPdf={isPdf}
              extractedText={selectedResult?.text || (selectedError ? String(selectedError) : "")}
              rawJson={selectedResult?.raw ?? selectedResult ?? { error: selectedError || "No output" }}
              models={models}
              selectedModel={selectedModel}
              onSelectModel={setSelectedModel}
            />

            <CompareModal
              open={isCompareOpen}
              onClose={() => setIsCompareOpen(false)}
              models={models}
              resultsByModel={resultsByModel}
              initialSelected={compareModels}
              minSelect={2}
              maxSelect={3}
              fileName={file?.name || "output"}
            />

            <MoreMetricsModal
              open={isMoreMetricsOpen}
              onClose={() => setIsMoreMetricsOpen(false)}
              title={`More Metrics — ${selectedModel || "model"}`}
              result={selectedResult}
            />
          </div>
        </section>
      </div>
    </div>
  );
}