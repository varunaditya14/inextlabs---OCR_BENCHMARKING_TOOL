import React, { useEffect, useMemo, useRef, useState } from "react";
import ExtractedTextBox from "./ExtractedTextBox";

// Helpers (defensive: supports {id,name,label} etc.)
function getModelId(m) {
  return m?.id ?? m?.value ?? m?.key ?? m?.model_id ?? m?.modelId ?? "";
}
function getModelLabel(m) {
  return m?.label ?? m?.name ?? m?.title ?? getModelId(m) ?? "model";
}

function clamp(n, a, b) {
  return Math.max(a, Math.min(b, n));
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

function downloadText(filename, text, mime = "text/plain") {
  const blob = new Blob([String(text ?? "")], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(String(text ?? ""));
    return true;
  } catch {
    return false;
  }
}

export default function CompareModal({
  open,
  onClose,
  models = [],
  resultsByModel = {},
  initialSelected = [],
  maxSelect = 3,
  minSelect = 2,
  fileName = "output", // optional (we will also fallback)
}) {
  const all = useMemo(
    () => models.map((m) => ({ id: getModelId(m), label: getModelLabel(m) })),
    [models]
  );

  const [selectedIds, setSelectedIds] = useState(() =>
    initialSelected.filter(Boolean).slice(0, maxSelect)
  );
  const [pickerOpen, setPickerOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // per-model collapsible sections
  // shape: { [modelId]: { json: boolean, md: boolean } }
  const [openSections, setOpenSections] = useState({});

  const toggleSection = (modelId, key) => {
    setOpenSections((prev) => {
      const curr = prev?.[modelId] || {};
      return { ...prev, [modelId]: { ...curr, [key]: !curr[key] } };
    });
  };

  // Close on ESC
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Sync selected when modal opens
  useEffect(() => {
    if (!open) return;
    const next = (initialSelected || []).filter(Boolean).slice(0, maxSelect);
    setSelectedIds(next);
    setPickerOpen(false);
    setIsFullscreen(false);
    setOpenSections({});
  }, [open]); // only on open changes

  const selectedModels = useMemo(() => {
    const map = new Map(all.map((m) => [m.id, m]));
    return selectedIds.map((id) => map.get(id)).filter(Boolean);
  }, [all, selectedIds]);

  const canClose = selectedIds.length >= minSelect;

  // Click outside close picker
  const pickerRef = useRef(null);
  useEffect(() => {
    if (!pickerOpen) return;
    const onDown = (e) => {
      if (!pickerRef.current) return;
      if (!pickerRef.current.contains(e.target)) setPickerOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [pickerOpen]);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const exists = prev.includes(id);
      if (exists) return prev.filter((x) => x !== id);
      if (prev.length >= maxSelect) return prev;
      return [...prev, id];
    });
  };

  const removeChip = (id) => {
    setSelectedIds((prev) => prev.filter((x) => x !== id));
  };

  if (!open) return null;

  return (
    <div className="compareOverlay" role="dialog" aria-modal="true">
      <div className={`compareModal ${isFullscreen ? "isFullscreen" : ""}`}>
        {/* Header */}
        <div className="compareHeader">
          <div className="compareTitleWrap">
            <div className="compareTitle">Compare Models</div>
            <div className="compareSubtitle"></div>
          </div>

          <div className="compareControls">
            {/* Multi-select chips */}
            <div className="compareMultiSelect" ref={pickerRef}>
              <button
                type="button"
                className="compareSelectButton"
                onClick={() => setPickerOpen((v) => !v)}
              >
                <span className="compareSelectLabel">Models</span>
                <span className="compareSelectCount">
                  {selectedIds.length}/{maxSelect}
                </span>
                <span className="compareChevron">▾</span>
              </button>

              <div className="compareChipsRow">
                {selectedModels.map((m) => (
                  <span key={m.id} className="compareChip">
                    {m.label}
                    <button
                      type="button"
                      className="compareChipX"
                      onClick={() => removeChip(m.id)}
                      aria-label={`Remove ${m.label}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
                {selectedModels.length === 0 && (
                  <span className="compareChipsHint">Pick 2–3 models</span>
                )}
              </div>

              {pickerOpen && (
                <div className="comparePicker">
                  {all.map((m) => {
                    const active = selectedIds.includes(m.id);
                    const disabled = !active && selectedIds.length >= maxSelect;
                    return (
                      <button
                        type="button"
                        key={m.id}
                        className={`comparePickerItem ${active ? "active" : ""}`}
                        onClick={() => toggleSelect(m.id)}
                        disabled={disabled}
                        title={disabled ? `Max ${maxSelect} models` : ""}
                      >
                        <span className="comparePickerDot" />
                        <span className="comparePickerText">{m.label}</span>
                        {active && <span className="comparePickerTick">Selected</span>}
                      </button>
                    );
                  })}
                  <div className="comparePickerFooter">
                    <span
                      className={`comparePickerNote ${
                        selectedIds.length < minSelect ? "warn" : ""
                      }`}
                    >
                      {selectedIds.length < minSelect
                        ? `Select at least ${minSelect} models`
                        : `You can select up to ${maxSelect} models`}
                    </span>
                    <button
                      type="button"
                      className="comparePickerDone"
                      onClick={() => setPickerOpen(false)}
                    >
                      Done
                    </button>
                  </div>
                </div>
              )}
            </div>

            <button
              type="button"
              className="compareIconBtn"
              onClick={() => setIsFullscreen((v) => !v)}
              title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            >
              {isFullscreen ? "⤢" : "⤢"}
            </button>

            <button
              type="button"
              className="compareCloseBtn"
              onClick={() => onClose?.()}
              title={!canClose ? `Pick at least ${minSelect} models` : "Close"}
            >
              ×
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="compareBody">
          <div
            className="compareGrid"
            style={{
              gridTemplateColumns: `repeat(${clamp(
                selectedModels.length || 2,
                2,
                3
              )}, minmax(0, 1fr))`,
            }}
          >
            {selectedModels.map((m) => {
              // IMPORTANT: resultsByModel[id] is ENTRY: {status, result, error}
              const entry = resultsByModel?.[m.id];
              const result = entry?.result || null;

              const text = result?.text ?? "";
              const latencyMs = result?.latency_ms ?? result?.backend_latency_ms ?? null;

              const billing = result?.billing || {};
              const costUsd = typeof billing?.cost_usd === "number" ? billing.cost_usd : null;

              const chars = typeof text === "string" ? text.length : 0;
              const words =
                typeof text === "string" ? (text.trim().match(/\S+/g) || []).length : 0;

              const linesArr =
                Array.isArray(result?.lines)
                  ? result.lines
                  : Array.isArray(result?.Lines)
                  ? result.Lines
                  : null;

              const lines = linesArr
                ? linesArr.length
                : typeof text === "string"
                ? text.split(/\r?\n/).length
                : 0;

              const seconds = latencyMs ? latencyMs / 1000 : null;
              const charsPerSec =
                seconds && seconds > 0 ? Math.round(chars / seconds) : null;

              // ✅ Make cost/1k always match outside behavior
              const costPer1kFromBackend =
                typeof billing?.cost_per_1k_chars_usd === "number"
                  ? billing.cost_per_1k_chars_usd
                  : null;

              const costPer1kComputed =
                costUsd != null && chars > 0 ? costUsd / (chars / 1000) : null;

              const costPer1k =
                costPer1kFromBackend != null ? costPer1kFromBackend : costPer1kComputed;

              const hasResult = !!result;

              // Collapsible contents
              const jsonOpen = !!openSections?.[m.id]?.json;
              const mdOpen = !!openSections?.[m.id]?.md;

              // "Markdown text": use extracted text as markdown for now (works + looks pro)
              const mdText = text || "";

              return (
                <div key={m.id} className="compareColCard">
                  <div className="compareColHeader">
                    <div className="compareModelPill">{m.label}</div>
                    <div className={`compareStatus ${hasResult ? "ok" : "missing"}`}>
                      {hasResult ? "Executed" : "Not executed"}
                    </div>
                  </div>

                  {/* ✅ Metrics: EXACTLY like outside (6 boxes) */}
                  <div className="compareMiniMetrics">
                    <div className="compareMiniMetric">
                      <div className="k">LATENCY</div>
                      <div className="v">
                        {latencyMs != null ? `${Math.round(latencyMs)} ms` : "—"}
                      </div>
                    </div>

                    <div className="compareMiniMetric">
                      <div className="k">CHARS PROCESSED</div>
                      <div className="v">{hasResult ? `${chars}` : "—"}</div>
                    </div>

                    <div className="compareMiniMetric">
                      <div className="k">WORDS</div>
                      <div className="v">{hasResult ? `${words}` : "—"}</div>
                    </div>

                    <div className="compareMiniMetric">
                      <div className="k">LINES</div>
                      <div className="v">{hasResult ? `${lines}` : "—"}</div>
                    </div>

                    <div className="compareMiniMetric">
                      <div className="k">CHARS / SEC</div>
                      <div className="v">
                        {hasResult && charsPerSec != null ? `${charsPerSec}` : "—"}
                      </div>
                    </div>

                    <div className="compareMiniMetric">
                      <div className="k">COST (USD)</div>
                      <div className="v">
                        {costUsd != null ? `$${costUsd.toFixed(6)}` : "—"}
                      </div>
                      <div
                        style={{
                          marginTop: 6,
                          fontSize: 12,
                          opacity: 0.72,
                        }}
                      >
                        Cost / 1K chars:{" "}
                        {costPer1k != null ? `$${costPer1k.toFixed(6)}` : "—"}
                      </div>
                    </div>
                  </div>

                  <div className="compareTextWrap">
                    {/* ✅ ExtractedTextBox used as-is (keeps your existing look) */}
                    {hasResult ? (
                      <div className="compareExtractWrap compareExtractWrap--noInnerScroll">
                        <ExtractedTextBox result={result} loading={false} />
                      </div>
                    ) : (
                      <div className="compareEmpty">
                        <div className="compareEmptyTitle">No result for this model yet</div>
                        <div className="compareEmptySub">
                          Run Benchmark once, then you can compare instantly.
                        </div>
                      </div>
                    )}

                    {/* ✅ Markdown collapsible bar */}
                    <div className="compareDrop">
                      <button
                        type="button"
                        className="compareDropHead"
                        onClick={() => toggleSection(m.id, "md")}
                        aria-expanded={mdOpen ? "true" : "false"}
                      >
                        <span className="compareDropArrow">{mdOpen ? "▼" : "▶"}</span>
                        <span className="compareDropTitle">Markdown Text</span>
                      </button>

                      {mdOpen && (
                        <div className="compareDropBody">
                          <div className="compareDropActions">
                            <button
                              type="button"
                              className="compareActionBtn"
                              onClick={() => copyToClipboard(mdText)}
                              disabled={!hasResult}
                            >
                              Copy
                            </button>
                            <button
                              type="button"
                              className="compareActionBtnPrimary"
                              onClick={() =>
                                downloadText(`${m.id}_${fileName}.md`, mdText, "text/markdown")
                              }
                              disabled={!hasResult}
                            >
                              Download MD
                            </button>
                          </div>

                          <pre className="compareDropPre">{mdText}</pre>
                        </div>
                      )}
                    </div>

                    {/* ✅ Raw JSON collapsible bar */}
                    <div className="compareDrop">
                      <button
                        type="button"
                        className="compareDropHead"
                        onClick={() => toggleSection(m.id, "json")}
                        aria-expanded={jsonOpen ? "true" : "false"}
                      >
                        <span className="compareDropArrow">{jsonOpen ? "▼" : "▶"}</span>
                        <span className="compareDropTitle">Raw JSON</span>
                      </button>

                      {jsonOpen && (
                        <div className="compareDropBody">
                          <div className="compareDropActions">
                            <button
                              type="button"
                              className="compareActionBtnPrimary"
                              onClick={() =>
                                downloadJson(`${m.id}_${fileName}.json`, result?.raw ?? result)
                              }
                              disabled={!hasResult}
                            >
                              Download JSON
                            </button>
                          </div>

                          <pre className="compareDropPre">
                            {JSON.stringify(result?.raw ?? result ?? {}, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {selectedIds.length < minSelect && (
            <div className="compareBottomHint">
              Select at least <b>{minSelect}</b> models to compare.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}