import React, { useEffect, useMemo, useRef, useState } from "react";

/**
 * ImageOverlay
 * Props:
 *  - fileUrl: string (URL.createObjectURL(file))
 *  - mimeType: string (file.type)
 *  - ocrResult: full OCR response object (contains lines/raw/text/etc)
 *
 * Behavior:
 *  - If PDF => show iframe preview
 *  - If Image => show image + draw boxes if available
 */
export default function ImageOverlay({ fileUrl, mimeType, ocrResult }) {
  const imgRef = useRef(null);
  const canvasRef = useRef(null);

  const [imgNatural, setImgNatural] = useState({ w: 0, h: 0 });
  const [imgClient, setImgClient] = useState({ w: 0, h: 0 });

  const type = (mimeType || "").toLowerCase();
  const isPdf = type.includes("pdf");
  const isImage = type.startsWith("image/");

  const isArr = Array.isArray;
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);

  // Convert box-like data into polygon [[x,y]..4]
  function toPolygon(box) {
    if (!box) return null;

    // polygon: [[x,y],[x,y],[x,y],[x,y]]
    if (
      isArr(box) &&
      box.length >= 4 &&
      isArr(box[0]) &&
      box.every((p) => isArr(p) && p.length >= 2 && isNum(p[0]) && isNum(p[1]))
    ) {
      return box.slice(0, 4).map((p) => [p[0], p[1]]);
    }

    // bbox: [x1,y1,x2,y2]
    if (isArr(box) && box.length === 4 && box.every(isNum)) {
      const [x1, y1, x2, y2] = box;
      return [
        [x1, y1],
        [x2, y1],
        [x2, y2],
        [x1, y2],
      ];
    }

    // object with bbox/box/points/polygon
    if (typeof box === "object") {
      return (
        toPolygon(box.polygon) ||
        toPolygon(box.points) ||
        toPolygon(box.box) ||
        toPolygon(box.bbox)
      );
    }

    return null;
  }

  // Extract polygons from ocrResult in a safe way
  function extractPolygons(res) {
    if (!res) return [];

    // 1) Prefer res.lines if iterable
    const lines = isArr(res.lines) ? res.lines : [];
    const polysFromLines = [];
    for (const ln of lines) {
      const poly =
        toPolygon(ln?.bbox) ||
        toPolygon(ln?.box) ||
        toPolygon(ln?.points) ||
        toPolygon(ln?.polygon) ||
        toPolygon(ln);
      if (poly) polysFromLines.push(poly);
    }
    if (polysFromLines.length) return polysFromLines;

    // 2) Try common raw nestings (Paddle/EasyOCR style)
    const raw = res.raw;

    const candidates = [
      raw,
      raw?.result,
      raw?.results,
      raw?.ocr,
      raw?.data,
      raw?.pages,
      raw?.predictions,
    ];

    const polys = [];

    for (const c of candidates) {
      if (!c) continue;

      // If array, iterate
      if (isArr(c)) {
        for (const item of c) {
          // Paddle often: [box, text, conf] where box is polygon
          if (isArr(item)) {
            const poly = toPolygon(item[0]) || toPolygon(item);
            if (poly) polys.push(poly);
          } else {
            const poly = toPolygon(item);
            if (poly) polys.push(poly);
          }
        }
      } else if (typeof c === "object") {
        // might have lines/boxes/words
        const inner =
          c.lines || c.boxes || c.words || c.detections || c.regions;
        if (isArr(inner)) {
          for (const item of inner) {
            const poly =
              toPolygon(item?.bbox) ||
              toPolygon(item?.box) ||
              toPolygon(item?.points) ||
              toPolygon(item?.polygon) ||
              toPolygon(item);
            if (poly) polys.push(poly);
          }
        }
      }

      if (polys.length) break;
    }

    return polys;
  }

  const polygons = useMemo(() => {
    if (!isImage) return [];
    return extractPolygons(ocrResult);
  }, [ocrResult, isImage]);

  // Track image displayed size to scale boxes
  useEffect(() => {
    if (!isImage) return;

    const img = imgRef.current;
    if (!img) return;

    const update = () => {
      setImgClient({ w: img.clientWidth || 0, h: img.clientHeight || 0 });
      setImgNatural({ w: img.naturalWidth || 0, h: img.naturalHeight || 0 });
    };

    update();

    const ro = new ResizeObserver(update);
    ro.observe(img);

    return () => ro.disconnect();
  }, [fileUrl, isImage]);

  // Draw polygons
  useEffect(() => {
    if (!isImage) return;

    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    const { w: cw, h: ch } = imgClient;
    const { w: nw, h: nh } = imgNatural;
    if (!cw || !ch || !nw || !nh) return;

    canvas.width = cw;
    canvas.height = ch;

    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, cw, ch);

    if (!polygons.length) return;

    const sx = cw / nw;
    const sy = ch / nh;

    ctx.lineWidth = 2;

    for (const poly of polygons) {
      if (!poly || poly.length < 4) continue;

      ctx.beginPath();
      ctx.moveTo(poly[0][0] * sx, poly[0][1] * sy);
      for (let i = 1; i < poly.length; i++) {
        ctx.lineTo(poly[i][0] * sx, poly[i][1] * sy);
      }
      ctx.closePath();
      ctx.stroke();
    }
  }, [polygons, imgClient, imgNatural, isImage]);

  // ---------------- UI ----------------
  if (!fileUrl) {
    return (
      <div className="preview-empty">
        <div className="preview-empty-title">No file selected</div>
        <div className="muted-small">Upload an image or PDF to preview here.</div>
      </div>
    );
  }

  // PDF Preview
  if (isPdf) {
    return (
      <div style={{ width: "100%", height: "100%", minHeight: 420 }}>
        <iframe
          title="PDF Preview"
          src={fileUrl}
          style={{
            width: "100%",
            height: "100%",
            border: 0,
            borderRadius: 12,
          }}
        />
      </div>
    );
  }

  // Image Preview + boxes overlay
  return (
    <div style={{ position: "relative", width: "100%", height: "100%", minHeight: 420 }}>
      <img
        ref={imgRef}
        src={fileUrl}
        alt="Preview"
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          display: "block",
          borderRadius: 12,
        }}
        onLoad={(e) => {
          const el = e.currentTarget;
          setImgNatural({ w: el.naturalWidth || 0, h: el.naturalHeight || 0 });
          setImgClient({ w: el.clientWidth || 0, h: el.clientHeight || 0 });
        }}
      />

      <canvas
        ref={canvasRef}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          pointerEvents: "none",
          borderRadius: 12,
        }}
      />
    </div>
  );
}
