export default function Navbar() {
  return (
    <div className="panel" style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <div style={{ fontWeight: 900, fontSize: 18 }}>OCR_TECT_PROTOTYPE</div>
      <div style={{ opacity: 0.75, fontSize: 13 }}>
        Upload → Choose model → Run OCR → Benchmark
      </div>
    </div>
  );
}
