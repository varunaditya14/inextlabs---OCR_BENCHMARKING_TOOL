// frontend/components/ModelDropdown.jsx
import React from "react";

export default function ModelDropdown({
  value,
  onChange,
  options = [],
  placeholder = "Select model",
  disabled = false,
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
    <div className="ocr-selectWrap">
      <select
        className="ocr-select"
        value={value || ""}
        onChange={(e) => onChange?.(e.target.value)}
        disabled={disabled}
      >
        {!value ? <option value="">{placeholder}</option> : null}

        {normalized.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}
          </option>
        ))}
      </select>
    </div>
  );
}
