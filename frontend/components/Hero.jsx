export default function Hero() {
  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <div style={{ fontWeight: 900, fontSize: 18, marginBottom: 6 }}>
        OCR Benchmarking Playground
      </div>
      <div style={{ opacity: 0.8 }}>
        Compare OCR models by output + bounding boxes + JSON + basic runtime metrics.
      </div>
    </div>
  );
}
