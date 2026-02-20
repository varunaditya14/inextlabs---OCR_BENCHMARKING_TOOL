import React, { useMemo } from "react";

export default function ExtractedTextBox({ result }) {
  const fullText = useMemo(() => {
    if (!result) return "";
    if (typeof result.text === "string") return result.text;
    return "";
  }, [result]);

  const meta = useMemo(() => {
    const model = result?.model || "—";
    const chars = fullText ? fullText.length : 0;

    // if backend gives structured lines, we can count them; otherwise split text
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
            disabled={!fullText}
            title="Copy extracted text"
          >
            Copy
          </button>
          <button
            className="extracted-text-box__btn extracted-text-box__btnPrimary"
            onClick={onDownload}
            disabled={!fullText}
            title="Download text as .txt"
          >
            Download TXT
          </button>
        </div>
      </div>

      <div className="extracted-text-box__body">
        {!fullText ? (
          <div className="extracted-text-box__empty">
            No text available yet. Run benchmark and select a model.
          </div>
        ) : (
          <div style={{ padding: "14px 16px", maxHeight: 320, overflow: "auto" }}>
            <div
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: 13,
                lineHeight: 1.6,
                color: "#111",
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