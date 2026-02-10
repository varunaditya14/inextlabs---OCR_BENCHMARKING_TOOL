import { useEffect, useMemo, useRef, useState } from "react";

/**
 * lines: [{ text, score, box }]
 * box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] (EasyOCR style)
 */
export default function ImageOverlay({ file, lines }) {
  const imgRef = useRef(null);
  const canvasRef = useRef(null);
  const [imgUrl, setImgUrl] = useState(null);

  useEffect(() => {
    if (!file) {
      setImgUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setImgUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const safeLines = useMemo(() => (Array.isArray(lines) ? lines : []), [lines]);

  function draw() {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;

    const ctx = canvas.getContext("2d");
    const w = img.clientWidth;
    const h = img.clientHeight;

    canvas.width = w;
    canvas.height = h;

    ctx.clearRect(0, 0, w, h);
    ctx.lineWidth = 2;

    const nw = img.naturalWidth || w;
    const nh = img.naturalHeight || h;
    const sx = w / nw;
    const sy = h / nh;

    for (const item of safeLines) {
      const box = item?.box;
      if (!Array.isArray(box) || box.length !== 4) continue;

      const pts = box.map(([x, y]) => [x * sx, y * sy]);

      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      ctx.lineTo(pts[1][0], pts[1][1]);
      ctx.lineTo(pts[2][0], pts[2][1]);
      ctx.lineTo(pts[3][0], pts[3][1]);
      ctx.closePath();
      ctx.stroke();
    }
  }

  useEffect(() => {
    draw();
    const onResize = () => draw();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imgUrl, safeLines]);

  if (!file) return null;

  return (
    <div className="overlayWrap">
      <img
        ref={imgRef}
        src={imgUrl}
        alt="uploaded"
        className="overlayImg"
        onLoad={draw}
      />
      <canvas ref={canvasRef} className="overlayCanvas" />
    </div>
  );
}
