import React, { useEffect, useRef, useState } from "react";

export default function ImageOverlay({ file, lines = [] }) {
  const wrapRef = useRef(null);
  const imgRef = useRef(null);
  const canvasRef = useRef(null);

  const [src, setSrc] = useState("");

  // ✅ stable blob URL lifecycle
  useEffect(() => {
    if (!file) {
      setSrc("");
      return;
    }
    const url = URL.createObjectURL(file);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    function render() {
      const wrap = wrapRef.current;
      const img = imgRef.current;
      const canvas = canvasRef.current;

      if (!wrap || !img || !canvas) return;
      if (!img.complete || !img.naturalWidth || !img.naturalHeight) return;

      const wrapRect = wrap.getBoundingClientRect();

      // ✅ Canvas matches wrapper size in real pixels
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(wrapRect.width * dpr));
      canvas.height = Math.max(1, Math.round(wrapRect.height * dpr));
      canvas.style.width = `${wrapRect.width}px`;
      canvas.style.height = `${wrapRect.height}px`;

      const ctx = canvas.getContext("2d");
      // draw in CSS pixels while canvas is scaled by DPR
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, wrapRect.width, wrapRect.height);

      // ✅ IMPORTANT: correct math for object-fit: contain
      const naturalW = img.naturalWidth;
      const naturalH = img.naturalHeight;

      const containerW = wrapRect.width;
      const containerH = wrapRect.height;

      const imageRatio = naturalW / naturalH;
      const containerRatio = containerW / containerH;

      let renderW, renderH;
      let offsetX = 0,
        offsetY = 0;

      if (imageRatio > containerRatio) {
        // image fits width, height letterboxed
        renderW = containerW;
        renderH = containerW / imageRatio;
        offsetY = (containerH - renderH) / 2;
      } else {
        // image fits height, width letterboxed
        renderH = containerH;
        renderW = containerH * imageRatio;
        offsetX = (containerW - renderW) / 2;
      }

      const scaleX = renderW / naturalW;
      const scaleY = renderH / naturalH;

      // box style (brand red)
      ctx.lineWidth = 2;
      ctx.strokeStyle = "rgba(240, 87, 66, 0.95)";
      ctx.fillStyle = "rgba(240, 87, 66, 0.10)";

      for (const l of lines || []) {
        const box = l?.box;
        if (!Array.isArray(box) || box.length !== 4) continue;

        const pts = box.map(([x, y]) => [
          offsetX + x * scaleX,
          offsetY + y * scaleY,
        ]);

        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        ctx.lineTo(pts[1][0], pts[1][1]);
        ctx.lineTo(pts[2][0], pts[2][1]);
        ctx.lineTo(pts[3][0], pts[3][1]);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    }

    // draw now + on resize
    render();
    window.addEventListener("resize", render);
    return () => window.removeEventListener("resize", render);
  }, [lines, src]);

  if (!src) return null;

  return (
    <div ref={wrapRef} className="overlay-wrap">
      <img
        ref={imgRef}
        src={src}
        alt="preview"
        className="overlay-img"
        onLoad={() => {
          // wait for layout before drawing
          requestAnimationFrame(() => {
            window.dispatchEvent(new Event("resize"));
          });
        }}
      />
      <canvas ref={canvasRef} className="overlay-canvas" />
    </div>
  );
}
