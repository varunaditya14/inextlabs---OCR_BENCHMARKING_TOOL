import React from "react";

export default function MetricSection({ title, children }) {
  return (
    <div className="rounded-2xl border border-[#f05742]/15 bg-white/70 p-4">
      <div className="text-sm font-extrabold text-[#f05742] tracking-wide uppercase mb-3">
        {title}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {children}
      </div>
    </div>
  );
}
