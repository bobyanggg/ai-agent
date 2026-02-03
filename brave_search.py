"""
Brave Search API crawler: find today's YouTube videos for given channel identifiers.
Uses Video Search with freshness=pd (past 24 hours) and filters for youtube.com/watch URLs.
"""

import re
from dataclasses import dataclass
from typing import List

import requests

BRAVE_VIDEO_SEARCH_URL = "https://api.search.brave.com/res/v1/videos/search"
YOUTUBE_WATCH_PATTERN = re.compile(
    r"https?://(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"
)


@dataclass
class VideoResult:
    """A YouTube video found by Brave Search."""

    video_id: str
    url: str
    title: str


def get_todays_videos(
    api_key: str,
    channel_identifier: str,
    *,
    freshness: str = "pd",
    count: int = 20,
) -> List[VideoResult]:
    """
    Search Brave for YouTube videos from the given channel in the last 24 hours.

    channel_identifier: Handle (e.g. @MKBHD) or channel name in quotes for exact match.
    freshness: pd = 24h, pw = 7d, pm = 31d, py = 1y.
    Returns deduplicated list of VideoResult (video_id, url, title).
    """
    # Target YouTube and the channel: site:youtube.com + channel handle/name
    query = f"site:youtube.com {channel_identifier}".strip()
    headers = {"X-Subscription-Token": api_key}
    params = {
        "q": query,
        "freshness": freshness,
        "count": count,
    }
    resp = requests.get(
        BRAVE_VIDEO_SEARCH_URL,
        headers=headers,
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    seen_ids: set[str] = set()
    results: List[VideoResult] = []
    for item in data.get("results") or []:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip() or "Untitled"
        match = YOUTUBE_WATCH_PATTERN.search(url)
        if not match:
            continue
        video_id = match.group(1)
        if video_id in seen_ids:
            continue
        seen_ids.add(video_id)
        # Normalize URL to canonical form
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        results.append(
            VideoResult(video_id=video_id, url=canonical_url, title=title)
        )
    return results
