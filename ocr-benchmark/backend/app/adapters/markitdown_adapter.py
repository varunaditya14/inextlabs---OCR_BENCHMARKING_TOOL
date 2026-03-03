import time
import tempfile
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Optional

from .base import OCRAdapter


def _clean_text(s: str) -> str:
    if not s:
        return ""
    # Remove HTML tags (MarkItDown sometimes includes them)
    s = re.sub(r"(?is)<[^>]+>", "", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def _norm_cell(x: Any) -> str:
    """
    Normalize a cell string for matching orphan lines:
    - strip
    - collapse spaces
    - remove trailing punctuation
    """
    if x is None:
        return ""
    s = str(x)
    s = s.replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(" :\t")
    return s


def _df_clean_and_merge(df) -> "Any":
    """
    Camelot often returns:
    - first row as header
    - multi-line descriptions split into next row with empty numeric columns

    We'll do conservative row-merge:
    If a row has text in col0 but numeric cols empty -> treat as continuation of previous row col0.
    Also trim empty columns.
    """
    try:
        import pandas as pd  # noqa
    except Exception:
        return df

    # Strip whitespace in all cells
    df = df.copy()
    for c in df.columns:
        df[c] = df[c].astype(str).map(lambda v: re.sub(r"\s+", " ", v.replace("\n", " ")).strip())

    # Drop fully empty columns
    def col_is_empty(col):
        vals = [v.strip() for v in col.tolist()]
        return all((v == "" or v.lower() == "nan") for v in vals)

    keep_cols = [c for c in df.columns if not col_is_empty(df[c])]
    if keep_cols:
        df = df[keep_cols]

    # Merge continuation rows (very common for "Description" columns)
    rows = df.values.tolist()
    if not rows:
        return df

    merged: List[List[str]] = []
    for r in rows:
        r = [("" if (str(x).lower() == "nan") else str(x)).strip() for x in r]
        if not merged:
            merged.append(r)
            continue

        # Heuristic: continuation row if:
        # - first cell has text
        # - AND most other cells are empty
        non0 = r[1:] if len(r) > 1 else []
        non0_nonempty = sum(1 for x in non0 if x.strip())
        if r[0].strip() and non0_nonempty == 0:
            # append to previous row first column
            prev = merged[-1]
            prev[0] = (prev[0].rstrip() + " " + r[0].lstrip()).strip()
            merged[-1] = prev
        else:
            merged.append(r)

    import pandas as pd  # noqa
    df2 = pd.DataFrame(merged, columns=list(df.columns))
    return df2


def _df_to_md(df) -> str:
    cols = [str(c) for c in list(df.columns)]
    md = []
    md.append("| " + " | ".join(cols) + " |")
    md.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for _, row in df.iterrows():
        cells = []
        for x in row.tolist():
            s = "" if x is None else str(x)
            s = s.replace("\n", " ").strip()
            s = s.replace("|", "\\|")
            cells.append(s)
        md.append("| " + " | ".join(cells) + " |")
    return "\n".join(md)


def _extract_tables_camelot(tmp_pdf_path: str) -> List[str]:
    """
    Try Camelot in both flavors:
      - lattice (works if there are ruling lines)
      - stream  (works if whitespace-separated)
    Return list of markdown tables.
    """
    try:
        import camelot  # noqa
    except Exception:
        return []

    tables_md: List[str] = []

    def run(flavor: str) -> List[Any]:
        try:
            # pages=all helps for multi-page invoices; you can limit if too slow
            return camelot.read_pdf(tmp_pdf_path, pages="all", flavor=flavor)
        except Exception:
            return []

    # Prefer lattice first (best structure if available)
    t_lattice = run("lattice")
    t_stream = run("stream") if not t_lattice or len(t_lattice) == 0 else []

    tables = []
    if t_lattice and len(t_lattice) > 0:
        tables = t_lattice
    elif t_stream and len(t_stream) > 0:
        tables = t_stream
    else:
        return []

    for i, t in enumerate(tables, start=1):
        try:
            df = t.df
            if df is None or df.empty:
                continue

            # Camelot gives header as first row often. Keep as-is but clean rows.
            # Convert first row into headers if it looks like headers.
            header_row = df.iloc[0].tolist() if len(df) > 0 else []
            header_row_norm = [_norm_cell(x) for x in header_row]
            header_nonempty = sum(1 for x in header_row_norm if x)

            if header_nonempty >= max(2, len(header_row_norm) // 2):
                df2 = df.iloc[1:].reset_index(drop=True)
                df2.columns = header_row_norm
            else:
                df2 = df

            df2 = _df_clean_and_merge(df2)
            md = _df_to_md(df2)

            tables_md.append(f"### Table {i}\n{md}")
        except Exception:
            continue

    return tables_md


def _build_table_cell_set(tables_md: List[str]) -> Set[str]:
    """
    Create a set of normalized cell strings from markdown tables
    so we can remove those exact orphan lines from the plain text.
    """
    cells: Set[str] = set()
    for block in tables_md:
        for ln in block.splitlines():
            ln = ln.strip()
            if not ln.startswith("|"):
                continue
            # skip separator rows
            if re.fullmatch(r"\|\s*[-:\s|]+\|", ln):
                continue
            parts = [p.strip() for p in ln.strip("|").split("|")]
            for p in parts:
                n = _norm_cell(p)
                if n:
                    cells.add(n)
    return cells


def _remove_orphan_table_lines(text: str, table_cells: Set[str]) -> str:
    """
    Remove lines from MarkItDown text that are likely leaked table cells,
    ONLY if we are confident they exist inside extracted tables.
    This is conservative and won't break other content.
    """
    if not text or not table_cells:
        return text

    lines = text.splitlines()
    out: List[str] = []

    for ln in lines:
        raw = ln.rstrip("\n")
        s = raw.strip()
        if not s:
            out.append(raw)
            continue

        ns = _norm_cell(s)

        # If a whole line exactly matches a table cell, drop it.
        if ns in table_cells:
            continue

        # Also drop if it's "amount-like" AND exists in table cells after normalization tweaks
        # Example: "25,000.00" / "-13,000.00"
        if re.fullmatch(r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?", ns) and ns in table_cells:
            continue

        out.append(raw)

    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


class MarkItDownAdapter(OCRAdapter):
    """
    MarkItDown = fast doc->text.
    Improvements:
      - Clean html-ish tags
      - Extract tables via Camelot (lattice + stream, multi-page)
      - Remove leaked/orphan table lines from plain text when tables exist
      - Append extracted tables as proper Markdown tables
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
        tables_md_blocks: List[str] = []

        try:
            # 1) MarkItDown conversion
            result = self._md.convert(tmp_path)
            text = getattr(result, "text_content", "") or ""
            text = _clean_text(text)

            # 2) Camelot tables for PDFs (text-based PDFs work best)
            if mime_type == "application/pdf":
                tables_md_blocks = _extract_tables_camelot(tmp_path)

                # If tables found, remove leaked table cells from flat text (safe)
                if tables_md_blocks:
                    cell_set = _build_table_cell_set(tables_md_blocks)
                    text = _remove_orphan_table_lines(text, cell_set)

        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

        # Merge output
        if tables_md_blocks:
            tables_md = "\n\n".join(tables_md_blocks).strip()
            combined = (
                (text.strip() + "\n\n---\n\n## Extracted Tables\n\n" + tables_md).strip()
                if text.strip()
                else ("## Extracted Tables\n\n" + tables_md).strip()
            )
        else:
            combined = text.strip()

        latency_ms = int((time.time() - t0) * 1000)
        return {
            "text": combined,
            "latency_ms": latency_ms,
            "raw": {
                "engine": "markitdown",
                "tables_extracted": bool(tables_md_blocks),
                "tables_count": len(tables_md_blocks),
            },
        }
