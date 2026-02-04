"""
YouTube channel crawler + summarizer + Telegram bot.

Run: python main.py
  Loads config from env (.env). Discovers today's videos per channel via YouTube Data API
  (if YOUTUBE_API_KEY set) or Brave Search; fetches transcripts, summarizes with Gemini,
  sends to Telegram.

Run: python main.py --video <url_or_id>
  Single-video mode: fetch transcript for the given video, summarize, send to Telegram.
  No channel discovery needed. Example: python main.py --video -jRur5z6TPk
"""

import argparse
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from brave_search import VideoResult, get_todays_videos as get_todays_videos_brave
from summarize import summarize_transcript
from telegram_send import send_video_summary
from transcript import get_transcript
from youtube_channel import get_todays_videos as get_todays_videos_youtube

# YouTube video ID from URL or raw ID (e.g. watch?v=ID, youtu.be/ID, or -jRur5z6TPk)
VIDEO_ID_FROM_URL = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})"
)
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROCESSED_STORE = Path(__file__).resolve().parent / "processed_videos.json"
TRANSCRIPTS_DIR = Path(__file__).resolve().parent / "transcripts"
SUMMARIES_DIR = Path(__file__).resolve().parent / "summaries"


def _video_id_from_input(s: str) -> str | None:
    """Extract YouTube video ID from a URL or return the string if it looks like an ID."""
    s = s.strip()
    if not s:
        return None
    m = VIDEO_ID_FROM_URL.search(s)
    if m:
        return m.group(1)
    # Raw ID: 11 chars, allowed [a-zA-Z0-9_-]
    if len(s) == 11 and re.match(r"^[a-zA-Z0-9_-]+$", s):
        return s
    return None


def _safe_filename_base(s: str, *, keep_at_prefix: bool = False) -> str:
    """Sanitize a string for filenames. Optionally keep a leading @."""
    s = s.strip()
    at = ""
    if keep_at_prefix and s.startswith("@"):
        at = "@"
        s = s[1:]
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s)
    s = s.strip("._-") or "item"
    return at + s


def _date_yyyymmdd_from_published_at(published_at: str | None) -> str:
    """
    Convert RFC3339 publishedAt (e.g. 2026-02-03T08:31:00Z) to YYYY_MM_DD.
    Falls back to today's UTC date if missing/unparseable.
    """
    if published_at:
        try:
            # Normalize trailing Z to +00:00 for fromisoformat
            s = published_at.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt.astimezone(UTC).date().strftime("%Y_%m_%d")
        except Exception:
            pass
    return datetime.now(UTC).date().strftime("%Y_%m_%d")


def _channel_base_for_filenames(handle: str | None, title: str | None, fallback: str) -> str:
    """Choose a stable channel base name for filenames (no leading @)."""
    raw = (handle or "").strip() or (title or "").strip() or fallback
    if raw.startswith("@"):
        raw = raw[1:]
    return _safe_filename_base(raw) or "channel"


def _fetch_youtube_title(video_id: str) -> str | None:
    """Fetch video title via YouTube oEmbed (no API key). Returns None on failure."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        title = (data.get("title") or "").strip()
        return title or None
    except Exception:
        return None


def _fetch_oembed_author_url(video_id: str) -> str | None:
    """Fetch channel URL from YouTube oEmbed (no API key)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        author_url = (data.get("author_url") or "").strip()
        return author_url or None
    except Exception:
        return None


def _handle_from_channel_url(url: str) -> str | None:
    """Extract @handle from a YouTube channel URL if present."""
    m = re.search(r"/@([A-Za-z0-9._-]+)", url)
    if not m:
        return None
    return "@" + m.group(1)


def _fetch_video_metadata(video_id: str, youtube_api_key: str | None) -> dict:
    """
    Fetch metadata for a YouTube video.

    Returns keys:
      - title (str|None)
      - channel_id (str|None)
      - channel_title (str|None)
      - channel_handle (str|None)  (best effort)
      - published_at (str|None)    (RFC3339, requires YouTube API key)
    """
    meta: dict = {
        "title": None,
        "channel_id": None,
        "channel_title": None,
        "channel_handle": None,
        "published_at": None,
    }

    # Title + (often) channel handle via oEmbed
    meta["title"] = _fetch_youtube_title(video_id)
    author_url = _fetch_oembed_author_url(video_id)
    if author_url:
        meta["channel_handle"] = _handle_from_channel_url(author_url)

    # Upload time + channel id/title via YouTube Data API (if configured)
    if youtube_api_key:
        try:
            resp = requests.get(
                YOUTUBE_VIDEOS_URL,
                params={"part": "snippet", "id": video_id, "key": youtube_api_key},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items") or []
            if items:
                snippet = items[0].get("snippet") or {}
                meta["published_at"] = snippet.get("publishedAt")
                meta["channel_id"] = snippet.get("channelId")
                meta["channel_title"] = snippet.get("channelTitle")
                # Prefer API title if available
                api_title = (snippet.get("title") or "").strip()
                if api_title:
                    meta["title"] = api_title
        except Exception as e:
            logger.info("YouTube API videos.list failed for %s: %s", video_id, e)

        # Try to resolve @handle via channels.list(customUrl) if possible
        if meta.get("channel_id"):
            try:
                resp = requests.get(
                    YOUTUBE_CHANNELS_URL,
                    params={
                        "part": "snippet",
                        "id": meta["channel_id"],
                        "key": youtube_api_key,
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items") or []
                if items:
                    snippet = items[0].get("snippet") or {}
                    custom_url = (snippet.get("customUrl") or "").strip()
                    if custom_url:
                        # customUrl may look like "@Handle", "HandleName", or a full URL
                        if custom_url.startswith("@"):
                            meta["channel_handle"] = custom_url
                        else:
                            maybe = _handle_from_channel_url(custom_url)
                            if maybe:
                                meta["channel_handle"] = maybe
                            elif "/" not in custom_url and " " not in custom_url:
                                # best-effort: treat as handle-like string
                                meta["channel_handle"] = "@" + custom_url.lstrip("@")
            except Exception as e:
                logger.info("YouTube API channels.list failed for %s: %s", video_id, e)

    return meta


def save_transcript_local(
    *,
    channel_base: str,
    yyyymmdd: str,
    transcript: str,
    video: VideoResult,
) -> None:
    """Append transcript to transcripts/channel_YYYY_MM_DD.txt."""
    if not transcript:
        return
    filename = f"{channel_base}_{yyyymmdd}.txt"
    try:
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        path = TRANSCRIPTS_DIR / filename
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{video.title}\n{video.url}\n\n")
            f.write(transcript.strip())
            f.write("\n\n" + ("-" * 80) + "\n\n")
    except Exception as e:
        logger.warning("Could not save transcript for %s (%s): %s", channel_base, video.video_id, e)


def save_summary_local(
    *,
    channel_base: str,
    yyyymmdd: str,
    summary_md: str,
    video: VideoResult,
) -> None:
    """Append summary to summaries/channel_YYYY_MM_DD.md."""
    if not summary_md:
        return
    filename = f"{channel_base}_{yyyymmdd}.md"
    try:
        SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
        path = SUMMARIES_DIR / filename
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"## {video.title}\n\n")
            f.write(f"{video.url}\n\n")
            f.write(summary_md.strip())
            f.write("\n\n---\n\n")
    except Exception as e:
        logger.warning("Could not save summary md for %s (%s): %s", channel_base, video.video_id, e)


def run_single_video(
    video_id: str,
    *,
    gemini_key: str,
    gemini_model: str | None,
    youtube_key: str | None,
    telegram_token: str,
    telegram_chat_id: str,
) -> None:
    """Fetch transcript, summarize, send to Telegram for one video. Optionally save transcript."""
    meta = _fetch_video_metadata(video_id, youtube_key)
    url = f"https://www.youtube.com/watch?v={video_id}"
    title = meta.get("title") or f"Video {video_id}"
    video = VideoResult(video_id=video_id, url=url, title=title)
    channel_base = _channel_base_for_filenames(
        meta.get("channel_handle"),
        meta.get("channel_title"),
        fallback="single",
    )
    yyyymmdd = _date_yyyymmdd_from_published_at(meta.get("published_at"))

    transcript = get_transcript(video_id)
    if not transcript:
        logger.error("No transcript for %s", video_id)
        raise SystemExit(1)
    save_transcript_local(
        channel_base=channel_base,
        yyyymmdd=yyyymmdd,
        transcript=transcript,
        video=video,
    )

    summary = summarize_transcript(
        transcript,
        api_key=gemini_key,
        model=gemini_model,
    )
    if not summary:
        logger.error("No summary for %s", video_id)
        raise SystemExit(1)
    save_summary_local(
        channel_base=channel_base,
        yyyymmdd=yyyymmdd,
        summary_md=summary,
        video=video,
    )
    if send_video_summary(telegram_token, telegram_chat_id, title, url, summary):
        logger.info("Sent summary for %s", video_id)
    else:
        logger.error("Failed to send Telegram message for %s", video_id)
        raise SystemExit(1)


def _safe_channel_name(channel: str) -> str:
    """Sanitize channel identifier for filenames."""
    name = channel.strip()
    if name.startswith("@"):
        name = name[1:]
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name or "channel"


def save_transcript(channel: str, transcript: str, *, video: VideoResult) -> None:
    """Backward-compat wrapper; prefer save_transcript_local()."""
    channel_base = _safe_channel_name(channel)
    yyyymmdd = datetime.now(UTC).date().strftime("%Y_%m_%d")
    save_transcript_local(channel_base=channel_base, yyyymmdd=yyyymmdd, transcript=transcript, video=video)


def load_processed() -> set[str]:
    """Load set of already-processed video IDs from JSON store."""
    if not PROCESSED_STORE.exists():
        return set()
    try:
        with open(PROCESSED_STORE) as f:
            data = json.load(f)
        return set(data.get("video_ids") or [])
    except Exception as e:
        logger.warning("Could not load processed store: %s", e)
        return set()


def save_processed(video_ids: set[str]) -> None:
    """Persist set of processed video IDs to JSON store."""
    try:
        with open(PROCESSED_STORE, "w") as f:
            json.dump({"video_ids": list(video_ids)}, f, indent=2)
    except Exception as e:
        logger.warning("Could not save processed store: %s", e)


def process_video(
    video: VideoResult,
    *,
    channel: str,
    gemini_key: str,
    gemini_model: str | None,
    youtube_key: str | None,
    telegram_token: str,
    telegram_chat_id: str,
    processed: set[str],
) -> None:
    """Fetch transcript, summarize, send to Telegram; skip if no transcript or on error."""
    if video.video_id in processed:
        logger.info("Skipping already processed: %s", video.video_id)
        return
    transcript = get_transcript(video.video_id)
    if not transcript:
        logger.info("No transcript for %s, skipping", video.video_id)
        return
    # Use upload time for filenames when possible (requires YOUTUBE_API_KEY)
    # Fall back to "today" if metadata fetch fails.
    meta = _fetch_video_metadata(video.video_id, youtube_key)
    channel_base = _channel_base_for_filenames(
        meta.get("channel_handle"),
        meta.get("channel_title"),
        fallback=channel,
    )
    yyyymmdd = _date_yyyymmdd_from_published_at(meta.get("published_at"))

    save_transcript_local(
        channel_base=channel_base,
        yyyymmdd=yyyymmdd,
        transcript=transcript,
        video=video,
    )
    summary = summarize_transcript(
        transcript,
        api_key=gemini_key,
        model=gemini_model,
    )
    if not summary:
        logger.warning("No summary for %s, skipping", video.video_id)
        return
    save_summary_local(
        channel_base=channel_base,
        yyyymmdd=yyyymmdd,
        summary_md=summary,
        video=video,
    )
    if send_video_summary(
        telegram_token,
        telegram_chat_id,
        video.title,
        video.url,
        summary,
    ):
        processed.add(video.video_id)
        logger.info("Sent summary for %s", video.video_id)
    else:
        logger.warning("Failed to send Telegram message for %s", video.video_id)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="YouTube transcript summarizer → Telegram. Use --video to process a single video by URL or ID."
    )
    parser.add_argument(
        "--video",
        nargs="+",
        metavar="URL_OR_ID",
        help="Single-video mode: process one or more videos (IDs or URLs). Example: --video -jRur5z6TPk https://youtu.be/abcdEFGhijk",
    )
    args = parser.parse_args()

    gemini_key = os.environ.get("GEMINI_API_KEY")
    youtube_key = os.environ.get("YOUTUBE_API_KEY")  # optional but needed for upload time
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    gemini_model = os.environ.get("GEMINI_MODEL") or None

    if not all([gemini_key, telegram_token, telegram_chat_id]):
        logger.error("Missing env: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        raise SystemExit(1)

    # Single-video mode: no channel discovery
    if args.video:
        raw_items: list[str] = []
        for item in args.video:
            raw_items.extend([p for p in item.split(",") if p.strip()])
        video_ids: list[str] = []
        for item in raw_items:
            vid = _video_id_from_input(item)
            if not vid:
                logger.error("Invalid video URL or ID: %s", item)
                raise SystemExit(1)
            video_ids.append(vid)
        for vid in video_ids:
            run_single_video(
                vid,
                gemini_key=gemini_key,
                gemini_model=gemini_model,
                youtube_key=youtube_key,
                telegram_token=telegram_token,
                telegram_chat_id=telegram_chat_id,
            )
        return

    # Channel mode: discover today's videos per channel
    brave_key = os.environ.get("BRAVE_API_KEY")
    # youtube_key already loaded above
    channels_raw = os.environ.get("YOUTUBE_CHANNELS", "")

    if not youtube_key and not brave_key:
        logger.error(
            "Missing env: set YOUTUBE_API_KEY (recommended for correct channel) or BRAVE_API_KEY"
        )
        raise SystemExit(1)

    channels = [c.strip() for c in channels_raw.split(",") if c.strip()]
    if not channels:
        logger.error("YOUTUBE_CHANNELS is empty; set e.g. YOUTUBE_CHANNELS=@Channel1,@Channel2")
        raise SystemExit(1)

    use_youtube = bool(youtube_key)
    processed = load_processed()
    try:
        for channel in channels:
            logger.info("Channel: %s", channel)
            try:
                if use_youtube:
                    videos = get_todays_videos_youtube(youtube_key, channel)
                else:
                    videos = get_todays_videos_brave(brave_key, channel)
            except Exception as e:
                logger.warning(
                    "Video fetch failed for %s: %s",
                    channel,
                    e,
                )
                continue
            if not videos:
                logger.info("No new videos today for %s", channel)
                continue
            for video in videos:
                try:
                    process_video(
                        video,
                        channel=channel,
                        gemini_key=gemini_key,
                        gemini_model=gemini_model,
                        youtube_key=youtube_key,
                        telegram_token=telegram_token,
                        telegram_chat_id=telegram_chat_id,
                        processed=processed,
                    )
                except Exception as e:
                    logger.warning("Error processing %s: %s", video.video_id, e)
    finally:
        save_processed(processed)


if __name__ == "__main__":
    main()
