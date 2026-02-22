import React, { useMemo, useState } from "react";

export default function ExtractedTextBox({ result, loading = false }) {
  const fullText = useMemo(() => {
    if (!result) return "";
    if (typeof result.text === "string") return result.text;
    return "";
  }, [result]);

  const [copied, setCopied] = useState(false);

  const meta = useMemo(() => {
    const model = result?.model || "—";
    const chars = fullText ? fullText.length : 0;

    const lineCount = Array.isArray(result?.lines)
      ? result.lines.length
      : fullText
      ? fullText.split(/\r?\n/).length
      : 0;

    return { model, chars, lineCount };
  }, [result, fullText]);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(fullText || "");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {}
  };

  const onDownload = () => {
    const blob = new Blob([fullText || ""], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result?.model || "ocr"}_extracted.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  // ✅ Premium lazy loading — shimmer + scanner sweep + soft cursor
  const Loader = () => {
    const line = (w, d = 0) => (
      <div
        style={{
          width: w,
          height: 12,
          borderRadius: 999,
          position: "relative",
          overflow: "hidden",
          background: "rgba(240,87,66,0.10)",
          border: "1px solid rgba(240,87,66,0.10)",
          boxShadow: "0 1px 0 rgba(16,24,40,0.03) inset",
          marginBottom: 10,
        }}
      >
        {/* shimmer sweep */}
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
        {/* scanner glow */}
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
      <div style={{ padding: "14px 16px", maxHeight: 320, overflow: "hidden" }}>
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
            @keyframes wbCursorPulse {
              0%, 100% { transform: scaleY(1); opacity: 0.65; }
              50% { transform: scaleY(1.18); opacity: 1; }
            }
          `}
        </style>

        {line("88%", 0)}
        {line("94%", 0.08)}
        {line("76%", 0.16)}
        {line("90%", 0.24)}
        {line("72%", 0.32)}
        {line("84%", 0.40)}

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 2 }}>
          <div style={{ flex: 1 }}>{line("60%", 0.48)}</div>
          <div
            aria-hidden="true"
            style={{
              width: 10,
              height: 18,
              borderRadius: 999,
              background: "rgba(240,87,66,0.65)",
              boxShadow: "0 0 0 4px rgba(240,87,66,0.10), 0 8px 20px rgba(240,87,66,0.18)",
              animation: "wbCursorPulse 1.05s ease-in-out infinite",
            }}
          />
        </div>

        <div style={{ marginTop: 10, fontSize: 12, color: "rgba(17,17,17,0.55)" }}>
          Processing… extracting text for this model
        </div>
      </div>
    );
  };

  const showEmpty = !loading && !fullText;

  return (
    <div className="extracted-text-box">
      <div className="extracted-text-box__header">
        <div>
          <div className="extracted-text-box__title">Extracted Text</div>
          <div className="extracted-text-box__meta">
            Model: {meta.model} • {meta.chars ? `${meta.chars} chars` : "—"} •{" "}
            {meta.lineCount ? `${meta.lineCount} lines` : "—"}
          </div>
        </div>

        <div className="extracted-text-box__actions">
          <button
            className="extracted-text-box__btn"
            onClick={onCopy}
            disabled={!fullText || loading}
            title="Copy extracted text"
            style={{
              transition: "transform 120ms ease, background 200ms ease, border-color 200ms ease",
              transform: copied ? "scale(0.98)" : "scale(1)",
              background: copied ? "rgba(34,197,94,0.12)" : undefined,
              borderColor: copied ? "rgba(34,197,94,0.35)" : undefined,
            }}
          >
            {copied ? "Copied ✓" : "Copy"}
          </button>

          <button
            className="extracted-text-box__btn extracted-text-box__btnPrimary"
            onClick={onDownload}
            disabled={!fullText || loading}
            title="Download text as .txt"
          >
            Download TXT
          </button>
        </div>
      </div>

      <div className="extracted-text-box__body">
        {loading ? (
          <Loader />
        ) : showEmpty ? (
          <div className="extracted-text-box__empty">
            No text available yet. Run benchmark and select a model.
          </div>
        ) : (
          <div
            style={{
              padding: "14px 16px",
              maxHeight: 320,
              overflow: "auto",
              overflowX: "auto",
            }}
          >
            <div
              style={{
                whiteSpace: "pre",
                wordBreak: "normal",
                fontSize: 13,
                lineHeight: 1.6,
                color: "#111",
                fontFamily:
                  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
              }}
            >
              {fullText}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}