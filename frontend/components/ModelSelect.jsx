// frontend/components/ModelSelect.jsx
import React from "react";

export default function ModelSelect({
  value,
  onChange,
  options = [],
  disabled = false,
  label = "",
}) {
  const list = Array.isArray(options) ? options : [];
  const normalized = list
    .map((m) => {
      if (typeof m === "string") return { id: m, label: m };
      if (m && typeof m === "object") return { id: m.id ?? m.value ?? "", label: m.label ?? m.name ?? m.id ?? "" };
      return null;
    })
    .filter((x) => x && x.id);

  return (
    <div className="modelSelect">
      {label ? <div className="modelSelect__label">{label}</div> : null}

      {/* ✅ WRAP + CLASSNAMES REQUIRED FOR CSS TO WORK */}
      <div className="ocr-selectWrap">
        <select
          className="ocr-select"
          value={value || ""}
          onChange={(e) => onChange?.(e.target.value)}
          disabled={disabled}
        >
          {normalized.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
