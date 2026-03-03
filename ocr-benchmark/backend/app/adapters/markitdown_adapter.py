import time
import tempfile
import re
from pathlib import Path
from typing import Any, Dict

from .base import OCRAdapter


def _clean_text(s: str) -> str:
    if not s:
        return ""
    # Remove HTML tags (MarkItDown sometimes includes them)
    s = re.sub(r"(?is)<[^>]+>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def _df_to_md(df) -> str:
    cols = list(df.columns)
    md = []
    md.append("| " + " | ".join(str(c) for c in cols) + " |")
    md.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for _, row in df.iterrows():
        md.append("| " + " | ".join(str(x) for x in row.tolist()) + " |")
    return "\n".join(md)


class MarkItDownAdapter(OCRAdapter):
    """
    MarkItDown = fast doc->text.
    We enhance it:
      - Clean html-ish tags
      - Try extracting tables via Camelot (text PDFs only) and append as markdown tables
    """

    def __init__(self):
        from markitdown import MarkItDown  # noqa

        self._md = MarkItDown(enable_plugins=True)

    def run(self, *, filename: str, mime_type: str, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        t0 = time.time()

        suffix = Path(filename).suffix or (".pdf" if mime_type == "application/pdf" else ".bin")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        text = ""
        tables_md = ""

        try:
            # 1) MarkItDown conversion
            result = self._md.convert(tmp_path)
            text = getattr(result, "text_content", "") or ""
            text = _clean_text(text)

            # 2) Optional: Camelot tables for PDFs (works for *text-based* PDFs)
            if mime_type == "application/pdf":
                try:
                    import camelot  # noqa

                    tables = camelot.read_pdf(tmp_path, pages="1")
                    if tables and len(tables) > 0:
                        parts = []
                        for i, t in enumerate(tables):
                            df = t.df
                            # Camelot gives header as first row often; keep as-is
                            parts.append(f"### Table {i+1}\n" + _df_to_md(df))
                        tables_md = "\n\n".join(parts).strip()
                except Exception:
                    # Camelot not installed or PDF not supported -> ignore
                    tables_md = ""

        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

        # Merge
        if tables_md:
            combined = (text + "\n\n---\n\n" + "## Extracted Tables\n\n" + tables_md).strip()
        else:
            combined = text

        latency_ms = int((time.time() - t0) * 1000)
        return {
            "text": combined,
            "latency_ms": latency_ms,
            "raw": {"engine": "markitdown", "tables_extracted": bool(tables_md)},
        }