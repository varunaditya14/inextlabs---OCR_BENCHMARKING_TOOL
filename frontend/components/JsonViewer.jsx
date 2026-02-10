export default function JsonViewer({ data }) {
  if (!data) return null;

  return (
    <div className="panel" style={{ gridColumn: "1 / -1" }}>
      <div className="panelTitle">JSON Output</div>
      <pre className="jsonBox">{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
