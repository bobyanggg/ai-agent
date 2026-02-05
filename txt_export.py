"""
Export summary text to a readable TXT format.

Key feature: convert Markdown pipe tables into aligned plain-text tables so they
look good in monospace viewers (including Telegram file preview).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_CELL_RE = re.compile(r"^\s*:?-{2,}:?\s*$")


def _strip_md_emphasis(s: str) -> str:
    # remove common bold markers; keep the content
    return s.replace("**", "").replace("__", "")


def _disp_width(s: str) -> int:
    """
    Approximate display width for monospace alignment.
    Treat non-ASCII as width 2 (good enough for CJK).
    """
    w = 0
    for ch in s:
        w += 1 if ord(ch) < 128 else 2
    return w


def _pad(s: str, width: int) -> str:
    pad = max(0, width - _disp_width(s))
    return s + (" " * pad)


def _wrap_text(s: str, max_width: int) -> list[str]:
    """Wrap text to max_width (by display width)."""
    s = s.strip()
    if not s:
        return [""]
    out: list[str] = []
    cur = ""
    cur_w = 0
    for ch in s:
        ch_w = 1 if ord(ch) < 128 else 2
        if cur and cur_w + ch_w > max_width:
            out.append(cur)
            cur = ch
            cur_w = ch_w
        else:
            cur += ch
            cur_w += ch_w
    if cur:
        out.append(cur)
    return out


@dataclass
class TableFormat:
    max_col_width: int = 48
    padding: int = 1


def _parse_table_block(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        if not _TABLE_ROW_RE.match(line):
            break
        # split: | a | b | -> ["a","b"]
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append([_strip_md_emphasis(c) for c in cells])
    return rows


def _is_separator_row(row: list[str]) -> bool:
    return bool(row) and all(_TABLE_SEP_CELL_RE.match(c) for c in row)


def _format_table(rows: list[list[str]], *, fmt: TableFormat) -> list[str]:
    if not rows:
        return []
    # Remove separator row if present as second row
    header = rows[0]
    data_rows = rows[1:]
    if data_rows and _is_separator_row(data_rows[0]):
        data_rows = data_rows[1:]

    ncols = max(len(r) for r in [header] + data_rows) if data_rows else len(header)
    # Normalize row lengths
    def norm(r: list[str]) -> list[str]:
        return r + [""] * (ncols - len(r))

    header = norm(header)
    data_rows = [norm(r) for r in data_rows]

    # Wrap cells
    wrapped_header = [(_wrap_text(c, fmt.max_col_width)) for c in header]
    wrapped_rows = [[_wrap_text(c, fmt.max_col_width) for c in r] for r in data_rows]

    # Column widths by max wrapped line width
    col_widths: list[int] = []
    for ci in range(ncols):
        maxw = 0
        for lines in [wrapped_header[ci]]:
            for l in lines:
                maxw = max(maxw, _disp_width(l))
        for r in wrapped_rows:
            for l in r[ci]:
                maxw = max(maxw, _disp_width(l))
        col_widths.append(min(maxw, fmt.max_col_width))

    # Helpers to render a logical row (possibly multi-line)
    def render_row(wrapped_cells: list[list[str]]) -> list[str]:
        height = max(len(c) for c in wrapped_cells) if wrapped_cells else 1
        out_lines: list[str] = []
        for i in range(height):
            parts: list[str] = []
            for ci, cell_lines in enumerate(wrapped_cells):
                txt = cell_lines[i] if i < len(cell_lines) else ""
                parts.append(_pad(txt, col_widths[ci]))
            out_lines.append(
                "|"
                + (" " * fmt.padding)
                + (" " * fmt.padding + "|" + " " * fmt.padding).join(parts)
                + (" " * fmt.padding)
                + "|"
            )
        return out_lines

    sep = (
        "|"
        + "+".join("-" * (w + 2 * fmt.padding) for w in col_widths)
        + "|"
    )

    out: list[str] = []
    out.extend(render_row(wrapped_header))
    out.append(sep)
    for r in wrapped_rows:
        out.extend(render_row(r))
    return out


def summary_markdown_to_pretty_txt(summary_md: str) -> str:
    """
    Convert a summary (which may contain Markdown pipe tables) into readable TXT.
    Non-table lines are kept, with bold markers stripped.
    """
    lines = summary_md.splitlines()
    out: list[str] = []
    i = 0
    tf = TableFormat()
    while i < len(lines):
        line = lines[i]
        if _TABLE_ROW_RE.match(line):
            # collect consecutive table-like lines
            j = i
            block: list[str] = []
            while j < len(lines) and _TABLE_ROW_RE.match(lines[j]):
                block.append(lines[j])
                j += 1
            rows = _parse_table_block(block)
            out.extend(_format_table(rows, fmt=tf))
            i = j
            continue
        out.append(_strip_md_emphasis(line).rstrip())
        i += 1
    # collapse excessive blank lines
    cleaned: list[str] = []
    blank = 0
    for l in out:
        if not l.strip():
            blank += 1
            if blank <= 2:
                cleaned.append("")
        else:
            blank = 0
            cleaned.append(l)
    return "\n".join(cleaned).strip() + "\n"

