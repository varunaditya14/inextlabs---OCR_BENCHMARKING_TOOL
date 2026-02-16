import React from "react";

export default function MetricCard({ icon, label, value, sub, tone = "base" }) {
  const toneMap = {
    base: {
      border: "border-[#f05742]/20",
      bg: "bg-white",
      iconBg: "bg-[#f05742]/10",
      iconText: "text-[#f05742]",
    },
    good: {
      border: "border-[#059669]/25",
      bg: "bg-white",
      iconBg: "bg-[#059669]/10",
      iconText: "text-[#059669]",
    },
    warn: {
      border: "border-[#d97706]/25",
      bg: "bg-white",
      iconBg: "bg-[#d97706]/10",
      iconText: "text-[#d97706]",
    },
    bad: {
      border: "border-[#dc2626]/25",
      bg: "bg-white",
      iconBg: "bg-[#dc2626]/10",
      iconText: "text-[#dc2626]",
    },
  };

  const t = toneMap[tone] || toneMap.base;

  return (
    <div
      className={[
        "rounded-2xl border shadow-sm",
        "p-4",
        "transition-all duration-200",
        "hover:shadow-md hover:-translate-y-[1px]",
        t.border,
        t.bg,
      ].join(" ")}
    >
      <div className="flex items-center gap-3">
        <div className={["h-10 w-10 rounded-xl flex items-center justify-center", t.iconBg].join(" ")}>
          <span className={["text-lg", t.iconText].join(" ")}>{icon}</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold tracking-wide text-gray-500 uppercase">
            {label}
          </div>
          <div className="text-lg font-extrabold text-gray-900 leading-tight truncate">
            {value ?? "—"}
          </div>
          {sub ? (
            <div className="text-xs text-gray-500 mt-1 truncate">{sub}</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
