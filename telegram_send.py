"""
Send summary messages to Telegram via Bot API.
One message per video: title, link, summary. Truncates or splits if over 4096 chars.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LENGTH = 4096


def send_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: Optional[str] = "HTML",
) -> bool:
    """
    Send a single message to the given Telegram chat.
    Returns True on success, False on failure. Logs errors.
    Truncates to MAX_MESSAGE_LENGTH if over limit.
    """
    url = TELEGRAM_SEND_URL.format(token=token)
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[: MAX_MESSAGE_LENGTH - 4] + "..."
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False


def send_video_summary(
    token: str,
    chat_id: str,
    title: str,
    url: str,
    summary: str,
) -> bool:
    """
    Send one message per video: title, link, and summary.
    Truncates or splits into multiple messages if over 4096 chars.
    """
    def escape(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    title_safe = escape(title)
    summary_safe = escape(summary)
    body = f"<b>{title_safe}</b>\n{url}\n\n{summary_safe}"
    if len(body) <= MAX_MESSAGE_LENGTH:
        return send_message(token, chat_id, body)

    header = f"<b>{title_safe}</b>\n{url}\n\n"
    if not send_message(token, chat_id, header):
        return False
    remaining = summary
    while remaining:
        chunk = remaining[:MAX_MESSAGE_LENGTH]
        remaining = remaining[MAX_MESSAGE_LENGTH:]
        if chunk.strip():
            if not send_message(token, chat_id, chunk, parse_mode=None):
                return False
    return True
