"""
Fetch YouTube video transcripts.

1. Tries youtube-transcript-api first (fast, uses YouTube captions when available).
2. If captions are disabled/missing and TRANSCRIPT_FALLBACK=whisper (or env unset and
   fallback enabled), downloads audio with yt-dlp and transcribes with OpenAI Whisper
   (like NoteGPT-style speech-to-text). Requires: yt-dlp, openai-whisper, ffmpeg.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

logger = logging.getLogger(__name__)


def _transcript_via_whisper(video_id: str) -> Optional[str]:
    """Download audio with yt-dlp and transcribe with OpenAI Whisper. Returns None on failure."""
    try:
        import whisper
        import yt_dlp
    except ImportError as e:
        logger.warning(
            "Whisper fallback unavailable for %s (install yt-dlp, openai-whisper, and ffmpeg): %s",
            video_id,
            e,
        )
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory(prefix="yt_transcript_") as tmp:
        out_path = Path(tmp) / "audio"
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": {"default": str(out_path) + ".%(ext)s"},
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "wav"},
            ],
            "quiet": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.warning("yt-dlp download failed for %s: %s", video_id, e)
            return None

        # Postprocessor renames to audio.wav
        audio_file = out_path.with_suffix(".wav")
        if not audio_file.exists():
            # Try any audio file in tmp
            candidates = list(Path(tmp).glob("audio.*"))
            if not candidates:
                logger.warning("No audio file produced for %s", video_id)
                return None
            audio_file = candidates[0]

        try:
            model = whisper.load_model(os.environ.get("WHISPER_MODEL", "base"))
            result = model.transcribe(str(audio_file), fp16=False)
            text = (result.get("text") or "").strip()
            return text or None
        except Exception as e:
            logger.warning("Whisper transcription failed for %s: %s", video_id, e)
            return None


def get_transcript(video_id: str) -> Optional[str]:
    """
    Fetch transcript for a YouTube video by ID.

    Tries YouTube captions first; if unavailable and TRANSCRIPT_FALLBACK=whisper,
    falls back to yt-dlp + Whisper (speech-to-text). Returns concatenated text or None.
    """
    # 1) Try YouTube captions
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
    except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound) as e:
        logger.info("Transcript unavailable for video %s (captions disabled/missing)", video_id)
        text = None
    except Exception as e:
        logger.warning("Failed to fetch transcript for %s: %s", video_id, e)
        text = None
    else:
        if transcript and transcript.snippets:
            parts = [s.text.strip() for s in transcript if s.text]
            text = " ".join(parts).strip() or None
        else:
            text = None

    if text:
        return text

    # 2) Optional Whisper fallback (like NoteGPT: transcribe from audio). Read env when called so load_dotenv() has run.
    fallback = os.environ.get("TRANSCRIPT_FALLBACK", "").strip().lower()
    if fallback != "whisper":
        return None
    logger.info("Trying Whisper fallback for video %s", video_id)
    return _transcript_via_whisper(video_id)
