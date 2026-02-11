import React from "react";

export default function Hero({ onRun }) {
  return (
    <section className="hero">
      <div className="hero-inner">
        <p className="hero-kicker">iNextLabs • OCR Benchmark</p>

        <h1 className="hero-title">
          OCR BENCHMARKING <span className="accent-dot">TOOL</span>
        </h1>

        <p className="hero-sub">
          OCR evaluation platform for benchmarking text extraction accuracy, structured outputs, and performance metrics across multiple engines.
        </p>

        <div className="hero-cta">
          <button className="cta-btn" onClick={onRun}>
            Run Benchmark
          </button>
        </div>
      </div>
    </section>
  );
}
