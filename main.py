"""
YouTube channel crawler + summarizer + Telegram bot.

Run: python main.py
Loads config from env (.env). Discovers today's videos per channel via YouTube Data API
(if YOUTUBE_API_KEY set) or Brave Search; fetches transcripts, summarizes with Gemini,
sends to Telegram. Optional idempotency: processed_videos.json stores processed video IDs.
"""

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from brave_search import VideoResult, get_todays_videos as get_todays_videos_brave
from summarize import summarize_transcript
from telegram_send import send_video_summary
from transcript import get_transcript
from youtube_channel import get_todays_videos as get_todays_videos_youtube

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROCESSED_STORE = Path(__file__).resolve().parent / "processed_videos.json"
TRANSCRIPTS_DIR = Path(__file__).resolve().parent / "transcripts"


def _safe_channel_name(channel: str) -> str:
    """Sanitize channel identifier for filenames."""
    name = channel.strip()
    if name.startswith("@"):
        name = name[1:]
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name or "channel"


def save_transcript(channel: str, transcript: str, *, video: VideoResult) -> None:
    """Append transcript to transcripts/{channel}_{YYYY-MM-DD}.txt."""
    if not transcript:
        return
    date_str = datetime.now(UTC).date().isoformat()
    filename = f"{_safe_channel_name(channel)}_{date_str}.txt"
    try:
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        path = TRANSCRIPTS_DIR / filename
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{video.title}\n{video.url}\n\n")
            f.write(transcript.strip())
            f.write("\n\n" + ("-" * 80) + "\n\n")
    except Exception as e:
        logger.warning("Could not save transcript for %s (%s): %s", channel, video.video_id, e)


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
    save_transcript(channel, transcript, video=video)
    summary = summarize_transcript(
        transcript,
        api_key=gemini_key,
        model=gemini_model,
    )
    if not summary:
        logger.warning("No summary for %s, skipping", video.video_id)
        return
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
    brave_key = os.environ.get("BRAVE_API_KEY")
    youtube_key = os.environ.get("YOUTUBE_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    channels_raw = os.environ.get("YOUTUBE_CHANNELS", "")
    gemini_model = os.environ.get("GEMINI_MODEL") or None

    if not all([gemini_key, telegram_token, telegram_chat_id]):
        logger.error("Missing env: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        raise SystemExit(1)
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
