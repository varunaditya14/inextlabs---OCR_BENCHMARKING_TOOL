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

/** ✅ Preview modal: LEFT input preview, RIGHT is 2 stacked halves (top text, bottom json)
 *  NEW:
 *   - model select inside header
 *   - fullscreen toggle
 *   - expand extracted/raw panels within modal
 */
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

  // null | "text" | "json"
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

  // When closing, reset fullscreen/pane for clean reopen
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

  // Right-side split (text + json)
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

  const panelTitleLeftStyle = {
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    minWidth: 0,
  };

  const panelTitleRightStyle = {
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
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
    <div
      className="pvOverlay"
      onMouseDown={() => {
        onClose();
      }}
    >
      <div className="pvModal" style={modalStyle} onMouseDown={(e) => e.stopPropagation()}>
        <div className="pvHeader">
          <div className="pvTitle">Input &amp; Output Preview</div>

          {/* ✅ NEW: model select + fullscreen + close */}
          <div style={headerRightStyle}>
            <select
              className="modelSelect2"
              value={selectedModel}
              onChange={(e) => onSelectModel?.(e.target.value)}
              disabled={!models?.length}
              style={{
                height: "34px",
                minWidth: "180px",
              }}
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
          {/* LEFT */}
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

          {/* RIGHT */}
          <div className="pvPane">
            <div className="pvPaneTitle">Output</div>

            <div style={outSplitStyle}>
              {(expandedPane === null || expandedPane === "text") && (
                <div style={boxStyle}>
                  <div style={titleStyle}>
                    <div style={panelTitleLeftStyle}>Extracted Text</div>
                    <div style={panelTitleRightStyle}>
                      <button
                        type="button"
                        style={smallIconBtnStyle}
                        onClick={() => toggleExpand("text")}
                        aria-label={
                          expandedPane === "text" ? "Collapse Extracted Text" : "Expand Extracted Text"
                        }
                        title={expandedPane === "text" ? "Collapse" : "Expand"}
                      >
                        {expandedPane === "text" ? "⤡" : "⤢"}
                      </button>
                    </div>
                  </div>
                  <div style={scrollWrapStyle}>
                    <pre style={preStyle}>{extractedText || ""}</pre>
                  </div>
                </div>
              )}

              {(expandedPane === null || expandedPane === "json") && (
                <div style={boxStyle}>
                  <div style={titleStyle}>
                    <div style={panelTitleLeftStyle}>Raw JSON</div>
                    <div style={panelTitleRightStyle}>
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

export default function OcrPlayground() {
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");

  const [file, setFile] = useState(null);
  const [executing, setExecuting] = useState(false);
  const [executed, setExecuted] = useState(false);

  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  const [resultsByModel, setResultsByModel] = useState({});

  // ✅ NEW (ADD-ONLY): compare modal state
  const [isCompareOpen, setIsCompareOpen] = useState(false);
  const [compareModels, setCompareModels] = useState([]); // 2–3 model ids

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

  // ✅ NEW: metrics lazy-loading (skeleton)
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
      costPer1k: costPer1k != null ? `$${costPer1k.toFixed(6)}` : "—",
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
  }

  // ✅ NEW (ADD-ONLY): open compare modal with a safe default 2-model selection
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
        {/* INPUT PANEL (UNCHANGED) */}
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
                <div className="metricsTitle2">Key Metrics</div>

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
                    <div className="metricSub2">
                      Cost / 1K chars: {metricsLoading ? "—" : summaryMetrics?.costPer1k || "—"}
                    </div>
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
          </div>
        </section>
      </div>
    </div>
  );
}