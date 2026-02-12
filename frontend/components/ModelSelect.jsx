import React, { useEffect, useMemo, useRef, useState } from "react";

const OPTIONS = [
  { label: "EasyOCR", value: "easyocr" },
  { label: "PaddleOCR", value: "paddleocr" },
  { label: "Dummy", value: "dummy" },
  { label: "Mistral OCR", value: "mistral" }

];

export default function ModelSelect({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  const selected = useMemo(
    () => OPTIONS.find((o) => o.value === value) || OPTIONS[0],
    [value]
  );

  useEffect(() => {
    function onDocClick(e) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target)) setOpen(false);
    }
    function onEsc(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, []);

  return (
    <div className="glassSelect" ref={rootRef}>
      <button
        type="button"
        className="glassSelectBtn"
        onClick={() => setOpen((s) => !s)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="glassSelectValue">{selected.label}</span>
        <span className={`glassSelectChevron ${open ? "isOpen" : ""}`}>⌄</span>
      </button>

      {open && (
        <div className="glassSelectMenu" role="listbox">
          {OPTIONS.map((opt) => {
            const active = opt.value === selected.value;
            return (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={active}
                className={`glassSelectItem ${active ? "isActive" : ""}`}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
