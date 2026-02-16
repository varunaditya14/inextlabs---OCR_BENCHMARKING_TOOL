import React, { useMemo } from "react";
import MetricCard from "./MetricCard";
import MetricSection from "./MetricSection";

/**
 * Works with ANY model:
 * - Uses backend-provided: latency_ms / backend_latency_ms / text / raw
 * - Computes: chars, words, lines, unique words, digits, cleanliness score, throughput
 * - Extracts tokens if found inside raw (Gemini/Mistral-like)
 */

function safeNum(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}

function countWords(text) {
  if (!text) return 0;
  const m = text.trim().match(/\S+/g);
  return m ? m.length : 0;
}

function countLines(text) {
  if (!text) return 0;
  const lines = text.split(/\r?\n/);
  return lines.filter((l) => l.trim().length > 0).length;
}

function uniqueWords(text) {
  if (!text) return 0;
  const tokens = (text.toLowerCase().match(/[a-z0-9]+/g) || []);
  return new Set(tokens).size;
}

function digitsCount(text) {
  if (!text) return 0;
  const m = text.match(/\d/g);
  return m ? m.length : 0;
}

function printableRatio(text) {
  if (!text || text.length === 0) return 0;
  let printable = 0;
  for (const ch of text) {
    const code = ch.charCodeAt(0);
    // printable ASCII + common whitespace
    if ((code >= 32 && code <= 126) || ch === "\n" || ch === "\r" || ch === "\t") printable++;
  }
  return printable / text.length;
}

function alnumRatio(text) {
  if (!text || text.length === 0) return 0;
  const alnum = (text.match(/[a-zA-Z0-9]/g) || []).length;
  return alnum / text.length;
}

function whitespaceRatio(text) {
  if (!text || text.length === 0) return 0;
  const ws = (text.match(/\s/g) || []).length;
  return ws / text.length;
}

function punctuationSpamRatio(text) {
  if (!text || text.length === 0) return 0;
  const punct = (text.match(/[^a-zA-Z0-9\s]/g) || []).length;
  return punct / text.length;
}

function hasRepeatingStreak(text) {
  if (!text) return false;
  // detect streaks like "||||||||||" or "__________"
  return /([^\w\s])\1{8,}/.test(text);
}

// Simple 0-100 cleanliness score (no ground truth needed)
function cleanlinessScore(text) {
  if (!text || text.trim().length === 0) return 0;

  const pr = printableRatio(text);         // good ↑
  const ar = alnumRatio(text);             // good ↑
  const wr = whitespaceRatio(text);         // too high bad
  const ps = punctuationSpamRatio(text);    // too high bad
  const streak = hasRepeatingStreak(text) ? 1 : 0;

  // normalize: start from 100 and subtract penalties
  let score = 100;

  // printable
  score -= (1 - pr) * 45;

  // alnum
  score -= (1 - ar) * 35;

  // whitespace penalty if extreme
  if (wr > 0.45) score -= (wr - 0.45) * 60;

  // punctuation spam
  if (ps > 0.18) score -= (ps - 0.18) * 120;

  // repeating streak
  score -= streak * 12;

  score = Math.max(0, Math.min(100, score));
  return Math.round(score);
}

// token extraction (best-effort, model-agnostic)
function extractTokens(raw) {
  if (!raw) return null;

  // Gemini-like: raw.tokenCount / raw.thoughtsTokenCount
  const tokenCount = safeNum(raw.tokenCount);
  const thoughts = safeNum(raw.thoughtsTokenCount);

  // Some APIs embed tokens deeper:
  // try common keys recursively
  const findKey = (obj, keys) => {
    if (!obj || typeof obj !== "object") return null;
    for (const k of keys) {
      if (obj[k] != null && Number.isFinite(Number(obj[k]))) return Number(obj[k]);
    }
    for (const v of Object.values(obj)) {
      const found = findKey(v, keys);
      if (found != null) return found;
    }
    return null;
  };

  const input = findKey(raw, ["input_tokens", "prompt_tokens", "inputTokenCount"]);
  const output = findKey(raw, ["output_tokens", "completion_tokens", "outputTokenCount"]);
  const total = findKey(raw, ["total_tokens", "totalTokenCount"]);

  // If only tokenCount+thoughts exist, treat:
  // inputTokens unknown, outputTokens = tokenCount, cache/thoughts separate
  return {
    input_tokens: input ?? null,
    output_tokens: output ?? tokenCount ?? null,
    total_tokens: total ?? (input != null && output != null ? input + output : null),
    thoughts_tokens: thoughts ?? null,
  };
}

function formatMs(ms) {
  const n = safeNum(ms);
  if (n == null) return "—";
  return `${Math.round(n)} ms`;
}

function toneFromScore(score) {
  if (score == null) return "base";
  if (score >= 85) return "good";
  if (score >= 65) return "base";
  if (score >= 45) return "warn";
  return "bad";
}

export default function ModelMetrics({ title = "MODEL METRICS", modelName, result, otherText }) {
  const computed = useMemo(() => {
    const text = result?.text || "";
    const latency = safeNum(result?.latency_ms ?? result?.backend_latency_ms ?? result?.latency ?? result?.backend_latency);
    const chars = text.length;
    const words = countWords(text);
    const lines = countLines(text);
    const uniq = uniqueWords(text);
    const digits = digitsCount(text);

    const clean = cleanlinessScore(text);

    const cps = latency && latency > 0 ? (chars / (latency / 1000)) : null;
    const wps = latency && latency > 0 ? (words / (latency / 1000)) : null;

    // similarity vs other model (Jaccard on word tokens)
    let sim = null;
    if (text && otherText) {
      const a = new Set((text.toLowerCase().match(/[a-z0-9]+/g) || []));
      const b = new Set((otherText.toLowerCase().match(/[a-z0-9]+/g) || []));
      const inter = [...a].filter((x) => b.has(x)).length;
      const union = new Set([...a, ...b]).size || 1;
      sim = inter / union;
    }

    const tokens = extractTokens(result?.raw);

    return {
      latency,
      chars,
      words,
      lines,
      uniq,
      digits,
      clean,
      cps,
      wps,
      sim,
      tokens,
    };
  }, [result, otherText]);

  const cleanTone = toneFromScore(computed.clean);
  const speedTone =
    computed.latency != null
      ? "base"
      : "warn";

  return (
    <div className="mt-5 rounded-3xl border border-[#f05742]/20 bg-white/70 shadow-sm p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="text-xs font-extrabold tracking-widest text-[#f05742]/80 uppercase">
            {title}
          </div>
          <div className="text-lg font-extrabold text-gray-900">
            {modelName ? modelName : "—"}
          </div>
        </div>

        {/* Winner badge placeholder (optional later) */}
        <div className="px-3 py-1 rounded-full border border-[#f05742]/20 bg-[#f05742]/10 text-[#f05742] text-xs font-bold">
          Benchmark Stats
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        <MetricSection title="Performance">
          <MetricCard
            icon="⏱"
            label="Total Latency"
            value={formatMs(computed.latency)}
            sub="End-to-end backend time"
            tone={speedTone}
          />
          <MetricCard
            icon="🚀"
            label="Chars / Sec"
            value={computed.cps != null ? computed.cps.toFixed(1) : "—"}
            sub="Normalized speed"
          />
          <MetricCard
            icon="📄"
            label="Words / Sec"
            value={computed.wps != null ? computed.wps.toFixed(1) : "—"}
            sub="Normalized speed"
          />
          <MetricCard
            icon="🔁"
            label="Agreement"
            value={computed.sim != null ? `${Math.round(computed.sim * 100)}%` : "—"}
            sub="Similarity vs other model"
          />
        </MetricSection>

        <MetricSection title="Quality">
          <MetricCard
            icon="🧼"
            label="Cleanliness Score"
            value={computed.clean != null ? `${computed.clean}/100` : "—"}
            sub="No ground-truth needed"
            tone={cleanTone}
          />
          <MetricCard
            icon="📊"
            label="Mean Confidence"
            value="N/A"
            sub="Only if model provides"
          />
          <MetricCard
            icon="⚠"
            label="Low-Conf %"
            value="N/A"
            sub="Only if model provides"
          />
          <MetricCard
            icon="🧩"
            label="Printable Ratio"
            value={result?.text ? `${Math.round(printableRatio(result.text) * 100)}%` : "—"}
            sub="Garbage detection"
          />
        </MetricSection>

        <MetricSection title="Output Stats">
          <MetricCard icon="🔤" label="Characters" value={computed.chars} />
          <MetricCard icon="📝" label="Words" value={computed.words} />
          <MetricCard icon="📚" label="Lines" value={computed.lines} />
          <MetricCard icon="🧠" label="Unique Words" value={computed.uniq} />
          <MetricCard icon="🔢" label="Digits" value={computed.digits} sub="Invoice-friendly" />
          <MetricCard
            icon="🧾"
            label="Whitespace Ratio"
            value={result?.text ? `${Math.round(whitespaceRatio(result.text) * 100)}%` : "—"}
            sub="Too high = messy"
          />
        </MetricSection>

        <MetricSection title="API / System">
          <MetricCard
            icon="⬇"
            label="Input Tokens"
            value={computed.tokens?.input_tokens ?? "N/A"}
            sub="API models only"
          />
          <MetricCard
            icon="⬆"
            label="Output Tokens"
            value={computed.tokens?.output_tokens ?? "N/A"}
            sub="API models only"
          />
          <MetricCard
            icon="∑"
            label="Total Tokens"
            value={computed.tokens?.total_tokens ?? "N/A"}
            sub="API models only"
          />
          <MetricCard
            icon="🧠"
            label="Thought Tokens"
            value={computed.tokens?.thoughts_tokens ?? "N/A"}
            sub="If provided by API"
          />
        </MetricSection>
      </div>
    </div>
  );
}
