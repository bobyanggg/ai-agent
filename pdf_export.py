"""
PDF export without third-party Python deps.

We generate a PDF by calling macOS CUPS `cupsfilter` (text/plain -> application/pdf),
which preserves Unicode (Chinese) correctly using system text rendering.

If `cupsfilter` is unavailable, we fall back to a very simple ASCII-only PDF generator
(not recommended for CJK).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def text_to_pdf_bytes(text: str) -> bytes:
    """
    Convert plain UTF-8 text to PDF bytes using CUPS `cupsfilter`.
    This produces output that matches what you see in the text/markdown file much better
    for CJK content than our previous raw PDF approach.
    """
    cupsfilter = "/usr/sbin/cupsfilter"
    if os.path.exists(cupsfilter):
        with tempfile.TemporaryDirectory(prefix="summary_pdf_") as tmp:
            in_path = Path(tmp) / "input.txt"
            in_path.write_text(text, encoding="utf-8")
            proc = subprocess.run(
                [cupsfilter, "-m", "application/pdf", str(in_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.startswith(b"%PDF"):
                return proc.stdout
            raise RuntimeError(
                f"cupsfilter failed (code={proc.returncode}): {proc.stderr.decode('utf-8', 'ignore')[:400]}"
            )

    # Fallback: minimal PDF (ASCII only)
    # If you hit this, install CUPS tools or run on macOS.
    header = f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
    payload = (header + text).encode("utf-8", "replace")
    # Not a real PDF fallback; keep explicit so callers don't silently get garbage.
    raise RuntimeError("cupsfilter not available; cannot generate a readable Unicode PDF.")


