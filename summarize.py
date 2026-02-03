"""
Summarize transcript text using Google Gemini API (google-genai SDK).
"""

import logging
from typing import Optional

from google import genai

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-1.5-flash"
# Extract key points; use tables only when data suits a table (pipe format: | col | col |)
SUMMARIZE_PROMPT = "幫我提取以上字幕重點。若有些資料適合用表格呈現，請用表格（| 欄位 | 內容 |）；其餘照常敘述即可。"


def summarize_transcript(
    transcript: str,
    *,
    api_key: str,
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Summarize transcript text using Gemini.

    Returns summary string, or None on error. Uses gemini-1.5-flash by default.
    """
    if not transcript or not transcript.strip():
        return None
    model_name = model or DEFAULT_MODEL
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=f"{SUMMARIZE_PROMPT}\n\n---\n\n{transcript[:150000]}",
        )
        if not response or not response.text:
            logger.warning("Gemini returned empty summary")
            return None
        return response.text.strip()
    except Exception as e:
        logger.warning("Gemini summarization failed: %s", e)
        return None
