import re
from typing import List, Tuple, Dict, Any

# token = (text, x1, y1, x2, y2)
Token = Tuple[str, float, float, float, float]


def html_to_markdown(text: str) -> str:
    if not text:
        return ""

    # <b>Ship To:</b> -> **Ship To:**
    text = re.sub(r"<\s*b\s*>", "**", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/\s*b\s*>", "**", text, flags=re.IGNORECASE)

    # remove other simple tags (keep content)
    text = re.sub(r"</?[^>]+>", "", text)

    return text


def _cluster_rows(tokens: List[Token], y_tol: float = 10.0) -> List[List[Token]]:
    """
    Group tokens into rows by their y-center.
    y_tol is in pixels; adjust if needed depending on your OCR resolution.
    """
    items = []
    for t, x1, y1, x2, y2 in tokens:
        yc = (y1 + y2) / 2.0
        items.append((yc, t, x1, y1, x2, y2))

    items.sort(key=lambda z: z[0])

    rows: List[List[Token]] = []
    cur: List[Token] = []
    cur_y = None

    for yc, t, x1, y1, x2, y2 in items:
        if cur_y is None:
            cur_y = yc
            cur = [(t, x1, y1, x2, y2)]
            continue

        if abs(yc - cur_y) <= y_tol:
            cur.append((t, x1, y1, x2, y2))
        else:
            rows.append(cur)
            cur = [(t, x1, y1, x2, y2)]
            cur_y = yc

    if cur:
        rows.append(cur)

    # sort tokens left->right in each row
    for r in rows:
        r.sort(key=lambda z: z[1])  # x1

    return rows


def _infer_columns(rows: List[List[Token]], max_cols: int = 8) -> List[float]:
    """
    Infer column x-centers using a simple clustering of token x-centers.
    """
    xs = []
    for r in rows:
        for _, x1, _, x2, _ in r:
            xs.append((x1 + x2) / 2.0)

    if not xs:
        return []

    xs.sort()
    cols = [xs[0]]
    for x in xs[1:]:
        if abs(x - cols[-1]) > 35:  # column separation threshold in px
            cols.append(x)
        else:
            cols[-1] = (cols[-1] + x) / 2.0

    # keep only first N columns
    return cols[:max_cols]


def _assign_to_columns(row: List[Token], col_centers: List[float]) -> List[str]:
    if not col_centers:
        # fallback: just join tokens
        return [" ".join([t[0] for t in row]).strip()]

    cells = [""] * len(col_centers)
    for text, x1, y1, x2, y2 in row:
        xc = (x1 + x2) / 2.0
        j = min(range(len(col_centers)), key=lambda k: abs(col_centers[k] - xc))
        if cells[j]:
            cells[j] += " " + text
        else:
            cells[j] = text

    return [c.strip() for c in cells]


def tokens_to_markdown_table(tokens: List[Token]) -> str:
    """
    Converts bbox tokens into a markdown table.
    This is heuristic-based (good for invoices/receipts).
    """
    rows = _cluster_rows(tokens, y_tol=10.0)
    if len(rows) < 2:
        return ""

    col_centers = _infer_columns(rows)

    grid = [_assign_to_columns(r, col_centers) for r in rows]

    # Trim empty trailing columns
    max_used = 0
    for r in grid:
        for i, c in enumerate(r):
            if c:
                max_used = max(max_used, i + 1)
    if max_used <= 1:
        return ""

    grid = [r[:max_used] for r in grid]

    # Create header from first row (if it looks like headers)
    header = grid[0]
    body = grid[1:]

    # If header is mostly empty, create generic headers
    if sum(1 for h in header if h) < max(2, len(header) // 2):
        header = [f"Col {i+1}" for i in range(len(header))]
        body = grid

    def md_escape(s: str) -> str:
        return (s or "").replace("\n", " ").replace("|", "\\|").strip()

    md = []
    md.append("| " + " | ".join(md_escape(h) for h in header) + " |")
    md.append("| " + " | ".join("---" for _ in header) + " |")
    for r in body:
        md.append("| " + " | ".join(md_escape(c) for c in r) + " |")

    return "\n".join(md)


def normalize_to_markdown(text: str, tokens: List[Token] = None) -> str:
    """
    1) Try bbox->table if tokens provided
    2) Else do html->markdown cleanup
    """
    if tokens:
        table_md = tokens_to_markdown_table(tokens)
        if table_md:
            # Keep original text on top (cleaned) + table below
            cleaned = html_to_markdown(text)
            # Avoid duplicating table lines if already included
            return cleaned.strip() + "\n\n" + table_md.strip()

    return html_to_markdown(text)