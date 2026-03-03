import os
import time
import json
import re
from typing import Any, Dict, List, Optional

from .base import OCRAdapter
from .docling_adapter import DoclingAdapter


def _extract_first_json(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    return m.group(0).strip() if m else ""


def _chunk_text(s: str, max_chars: int) -> str:
    if not s:
        return ""
    s = s.strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n\n[TRUNCATED]\n"


def _escape_md_cell(x: Any) -> str:
    s = "" if x is None else str(x)
    s = s.replace("\n", " ").strip()
    s = s.replace("|", "\\|")
    return s


def _render_markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    if not headers:
        w = 0
        for r in rows or []:
            if isinstance(r, list):
                w = max(w, len(r))
        headers = [f"col_{i+1}" for i in range(w)]

    hdr = "| " + " | ".join(_escape_md_cell(h) for h in headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"

    out_rows = []
    for r in rows or []:
        r = r if isinstance(r, list) else [r]
        r = r + [""] * (len(headers) - len(r))
        out_rows.append("| " + " | ".join(_escape_md_cell(c) for c in r[: len(headers)]) + " |")

    return "\n".join([hdr, sep] + out_rows)


def _json_to_pretty_text(structured: Dict[str, Any]) -> str:
    lines: List[str] = []

    meta = structured.get("meta") or {}
    doc_type = meta.get("document_type")
    lang = meta.get("language")
    if doc_type or lang:
        lines.append("## Document Meta")
        if doc_type:
            lines.append(f"- **document_type**: {doc_type}")
        if lang:
            lines.append(f"- **language**: {lang}")
        lines.append("")

    key_values = structured.get("key_values") or []
    if isinstance(key_values, list) and key_values:
        lines.append("## Key Fields")
        for kv in key_values:
            if not isinstance(kv, dict):
                continue
            k = kv.get("key")
            v = kv.get("value")
            if k is None and v is None:
                continue
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    sections = structured.get("sections") or []
    if isinstance(sections, list) and sections:
        lines.append("## Sections")
        lines.append("")
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            title = (sec.get("title") or "").strip()
            content = (sec.get("content") or "").strip()
            if title:
                lines.append(f"### {title}")
            if content:
                lines.append(content)
            lines.append("")

    tables = structured.get("tables") or []
    if isinstance(tables, list) and tables:
        lines.append("## Extracted Tables")
        lines.append("")
        for i, t in enumerate(tables, start=1):
            if not isinstance(t, dict):
                continue
            title = t.get("title")
            headers = t.get("headers") or []
            rows = t.get("rows") or []
            lines.append(f"### Table {i}" + (f": {title}" if title else ""))
            try:
                lines.append(_render_markdown_table(headers, rows))
            except Exception:
                lines.append("(Could not render table)")
            lines.append("")

    return "\n".join(lines).strip()


def _docling_fallback_structured(doc_md: str) -> str:
    # Return ONLY docling extracted markdown (no extra wrapper text)
    return (doc_md or "").strip()

    out: List[str] = []
    out.append("## LangExtract (Fallback Mode)")
    out.append("")
    out.append(
        "> Gemini quota/rate limit hit. Showing Docling-structured extraction instead.\n"
        "> This keeps output usable without breaking other models."
    )
    out.append("")
    out.append("## Document (Docling Markdown)")
    out.append("")
    out.append(doc_md)
    return "\n".join(out).strip()


def _is_quota_error(e: Exception) -> bool:
    s = repr(e).lower()
    return ("429" in s) or ("resource_exhausted" in s) or ("quota" in s) or ("rate limit" in s)


class LangExtractAdapter(OCRAdapter):
    """
    Produces USER-FRIENDLY structured markdown output (like other models),
    while keeping the full structured JSON in raw["structured"] (when available).

    Important:
    - LangExtract uses Gemini under the hood -> can throw 429.
    - On 429, fallback to Docling-only structured markdown instead of failing.
    """

    def __init__(self):
        import langextract as lx  # noqa: F401

        self.gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not self.gemini_key:
            raise RuntimeError("GEMINI_API_KEY missing in backend/.env (required for langextract).")

        self.model_id = os.getenv("LANGEXTRACT_MODEL", "gemini-2.5-flash").strip()
        self.max_input_chars = int(os.getenv("LANGEXTRACT_MAX_CHARS", "12000"))

        # retries for transient Gemini errors
        self.max_retries = int(os.getenv("LANGEXTRACT_MAX_RETRIES", "2"))
        self.base_backoff_sec = float(os.getenv("LANGEXTRACT_BACKOFF_SEC", "1.5"))

        self._docling = DoclingAdapter()

    def run(self, *, filename: str, mime_type: str, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        import langextract as lx

        t0 = time.time()

        # 1) Docling base extraction (always)
        base = self._docling.run(filename=filename, mime_type=mime_type, image_bytes=image_bytes)
        doc_text_md = (base.get("text") or "").strip()

        if not doc_text_md:
            latency_ms = int((time.time() - t0) * 1000)
            return {
                "text": "",
                "latency_ms": latency_ms,
                "raw": {"engine": "langextract", "note": "Docling returned empty text."},
            }

        # Keep input bounded for Gemini
        doc_text_for_llm = _chunk_text(doc_text_md, self.max_input_chars)

        # 2) Schema prompt (strict JSON)
        prompt = (
            "Convert the following document into STRICT JSON ONLY.\n"
            "Return valid JSON only. No markdown. No extra text.\n\n"
            "Schema:\n"
            "{\n"
            '  "meta": {"document_type": "invoice|receipt|statement|unknown", "language": "string|null"},\n'
            '  "sections": [{"title": "string", "content": "string"}],\n'
            '  "tables": [{"title": "string|null", "headers": ["c1","c2"], "rows": [["..."]]}],\n'
            '  "key_values": [{"key": "string", "value": "string"}]\n'
            "}\n\n"
            "Rules:\n"
            "- Do NOT summarize; keep as much content as possible.\n"
            "- Any table-like region must go into tables[].\n"
            "- Everything else goes to sections[].\n"
            "- Add important invoice fields into key_values[].\n"
        )

        examples = [
            lx.data.ExampleData(
                text="Invoice No: INV-001\nDate: 2025-01-01\nItem Qty Price\nA 1 10\nTotal 10",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="structured_json",
                        extraction_text=json.dumps(
                            {
                                "meta": {"document_type": "invoice", "language": "en"},
                                "sections": [{"title": "Header", "content": "Invoice No: INV-001\nDate: 2025-01-01"}],
                                "tables": [
                                    {
                                        "title": "Line Items",
                                        "headers": ["Item", "Qty", "Price"],
                                        "rows": [["A", "1", "10"]],
                                    }
                                ],
                                "key_values": [
                                    {"key": "invoice_number", "value": "INV-001"},
                                    {"key": "total", "value": "10"},
                                ],
                            }
                        ),
                        attributes={},
                    )
                ],
            )
        ]

        last_err: Optional[Exception] = None
        raw_text = ""

        for attempt in range(self.max_retries + 1):
            try:
                result = lx.extract(
                    text_or_documents=doc_text_for_llm,
                    prompt_description=prompt,
                    examples=examples,
                    model_id=self.model_id,
                    api_key=self.gemini_key,
                )

                extractions = getattr(result, "extractions", None) or []
                raw_text = (getattr(extractions[0], "extraction_text", "") if extractions else "") or ""
                raw_text = raw_text.strip()

                json_text = _extract_first_json(raw_text)
                structured = None
                if json_text:
                    try:
                        structured = json.loads(json_text)
                    except Exception:
                        structured = None

                latency_ms = int((time.time() - t0) * 1000)

                if structured is None:
                    # If JSON failed, return Docling structured view (still useful)
                    return {
                        "text": _docling_fallback_structured(doc_text_md),
                        "latency_ms": latency_ms,
                        "raw": {
                            "engine": "langextract",
                            "provider": "gemini",
                            "model_id": self.model_id,
                            "note": "JSON parse failed; showing Docling fallback.",
                            "raw_model_output": raw_text[:2000],
                        },
                    }

                pretty_text = _json_to_pretty_text(structured)

                return {
                    "text": pretty_text,
                    "latency_ms": latency_ms,
                    "raw": {
                        "engine": "langextract",
                        "provider": "gemini",
                        "model_id": self.model_id,
                        "max_input_chars": self.max_input_chars,
                        "structured": structured,
                    },
                }

            except Exception as e:
                last_err = e

                # If quota/rate limit, fallback immediately (don't keep hammering)
                if _is_quota_error(e):
                    latency_ms = int((time.time() - t0) * 1000)
                    return {
                        "text": _docling_fallback_structured(doc_text_md),
                        "latency_ms": latency_ms,
                        "raw": {
                            "engine": "langextract",
                            "provider": "gemini",
                            "model_id": self.model_id,
                            "note": "Gemini quota/rate limit hit; showing Docling fallback.",
                            "error": repr(e),
                        },
                    }

                # backoff then retry
                time.sleep(self.base_backoff_sec * (attempt + 1))

        latency_ms = int((time.time() - t0) * 1000)
        return {
            "text": _docling_fallback_structured(doc_text_md),
            "latency_ms": latency_ms,
            "raw": {
                "engine": "langextract",
                "provider": "gemini",
                "model_id": self.model_id,
                "note": "LangExtract failed after retries; showing Docling fallback.",
                "error": repr(last_err),
            },
        }

