"""
Export summary markdown-ish text to a self-contained HTML document.

Key feature: convert Markdown pipe tables into real HTML <table> so they render nicely.
This HTML can be sent as a Telegram document and opened in any browser.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass


_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_CELL_RE = re.compile(r"^\s*:?-{2,}:?\s*$")


def _strip_md_emphasis(s: str) -> str:
    return s.replace("**", "").replace("__", "")


def _inline_format(s: str) -> str:
    """
    Very small inline formatter:
    - escape HTML
    - convert **bold** to <b>...</b>
    - convert literal <br> / <br/> (common from models) into real HTML line breaks
    """
    # Normalize model-produced line breaks to newlines before escaping.
    # This prevents them from showing up as literal "&lt;br&gt;" in the rendered page.
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)

    # Escape first, then re-insert tags for bold via a regex on escaped text.
    esc = html.escape(s, quote=False)
    # bold: **text**
    esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
    # Turn newlines into HTML line breaks inside cells/paragraph lines.
    esc = esc.replace("\n", "<br/>")
    return esc


def _parse_table_block(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        if not _TABLE_ROW_RE.match(line):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append([_strip_md_emphasis(c) for c in cells])
    return rows


def _is_separator_row(row: list[str]) -> bool:
    return bool(row) and all(_TABLE_SEP_CELL_RE.match(c) for c in row)


def _table_to_html(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    body_rows = rows[1:]
    if body_rows and _is_separator_row(body_rows[0]):
        body_rows = body_rows[1:]

    ncols = max(len(r) for r in [header] + body_rows) if body_rows else len(header)

    def norm(r: list[str]) -> list[str]:
        return r + [""] * (ncols - len(r))

    header = norm(header)
    body_rows = [norm(r) for r in body_rows]

    thead = "<thead><tr>" + "".join(f"<th>{_inline_format(c)}</th>" for c in header) + "</tr></thead>"
    tbody = "<tbody>" + "".join(
        "<tr>" + "".join(f"<td>{_inline_format(c)}</td>" for c in row) + "</tr>" for row in body_rows
    ) + "</tbody>"
    return f"<table>{thead}{tbody}</table>"


@dataclass
class HtmlStyle:
    title: str = "Summary"


DEFAULT_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", "PingFang SC", "Microsoft YaHei", Arial, sans-serif; line-height: 1.55; padding: 16px; }
h1,h2,h3 { margin: 16px 0 8px; }
p { margin: 8px 0; white-space: pre-wrap; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th, td { border: 1px solid #333; padding: 6px 8px; vertical-align: top; }
th { background: #f2f2f2; }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
"""


def summary_markdown_to_html_doc(
    summary_md: str,
    *,
    title: str,
    header_lines: list[str] | None = None,
) -> str:
    """
    Convert markdown-ish summary to a single HTML document.

    Supports:
    - #/##/### headings
    - bullet lists starting with '-' or '*'
    - pipe tables
    - paragraphs
    """
    lines = summary_md.splitlines()
    out: list[str] = []

    # Optional header info
    if header_lines:
        out.append("<div class='meta'>")
        for hl in header_lines:
            out.append(f"<p>{_inline_format(hl)}</p>")
        out.append("</div>")

    i = 0
    in_ul = False
    while i < len(lines):
        line = lines[i].rstrip()

        # Table block
        if _TABLE_ROW_RE.match(line):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            j = i
            block: list[str] = []
            while j < len(lines) and _TABLE_ROW_RE.match(lines[j]):
                block.append(lines[j])
                j += 1
            rows = _parse_table_block(block)
            out.append(_table_to_html(rows))
            i = j
            continue

        # Headings
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            level = len(m.group(1))
            text = m.group(2).strip()
            out.append(f"<h{level}>{_inline_format(text)}</h{level}>")
            i += 1
            continue

        # Bullet list
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline_format(m.group(1).strip())}</li>")
            i += 1
            continue

        # Blank line
        if not line.strip():
            if in_ul:
                out.append("</ul>")
                in_ul = False
            i += 1
            continue

        # Paragraph
        if in_ul:
            out.append("</ul>")
            in_ul = False
        out.append(f"<p>{_inline_format(line)}</p>")
        i += 1

    if in_ul:
        out.append("</ul>")

    body = "\n".join(out)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>{DEFAULT_CSS}</style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  {body}
</body>
</html>
"""

