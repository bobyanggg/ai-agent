"""
YouTube Data API v3: fetch today's videos for a channel by handle (e.g. @RhinoFinance).
Returns the same VideoResult shape as brave_search for drop-in use.
Use this when you need videos actually uploaded by the channel (Brave search can return wrong channel).
"""

from datetime import UTC, datetime
from typing import List

import requests

from brave_search import VideoResult

YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def _channel_id_for_handle(api_key: str, handle: str) -> str | None:
    """Resolve @handle (or handle without @) to YouTube channel ID. Returns None on error."""
    handle = handle.strip()
    if handle.startswith("@"):
        handle = handle[1:]
    if not handle:
        return None
    params = {
        "part": "id",
        "forHandle": handle,
        "key": api_key,
    }
    resp = requests.get(YOUTUBE_CHANNELS_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items") or []
    if not items:
        return None
    return items[0].get("id")


def get_todays_videos(
    api_key: str,
    channel_identifier: str,
    *,
    count: int = 20,
) -> List[VideoResult]:
    """
    Get today's videos uploaded by the given channel using YouTube Data API v3.

    channel_identifier: Handle with or without @ (e.g. @RhinoFinance or RhinoFinance).
    Returns list of VideoResult (video_id, url, title) for videos published since start of today UTC.
    """
    channel_id = _channel_id_for_handle(api_key, channel_identifier)
    if not channel_id:
        return []

    # Start of today UTC (RFC 3339: YYYY-MM-DDTHH:MM:SSZ only — no +00:00 and Z together)
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    published_after = today_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "maxResults": min(count, 50),
        "publishedAfter": published_after,
        "key": api_key,
    }
    resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    results: List[VideoResult] = []
    for item in data.get("items") or []:
        vid = item.get("id", {}).get("videoId")
        if not vid:
            continue
        snippet = item.get("snippet") or {}
        title = (snippet.get("title") or "").strip() or "Untitled"
        results.append(
            VideoResult(
                video_id=vid,
                url=f"https://www.youtube.com/watch?v={vid}",
                title=title,
            )
        )
    return results
