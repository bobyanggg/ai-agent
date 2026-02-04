# YouTube Channel Crawler + Summarizer + Telegram Bot

Crawls configured YouTube channels for new uploads, fetches transcripts, summarizes with Gemini, and sends summaries to Telegram.

## Requirements

- Python 3.10+
- API keys: Brave Search or YouTube Data API, Google Gemini, Telegram Bot

## Setup

1. Clone or copy this project, then create a virtualenv and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your keys:

   - `BRAVE_API_KEY` — from [Brave Search API](https://api.search.brave.com/) or set `YOUTUBE_API_KEY` (see Optional)
   - `GEMINI_API_KEY` — Google AI / Gemini API key
   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `TELEGRAM_CHAT_ID` — message your bot, then call `getUpdates` or use [@userinfobot](https://t.me/userinfobot)
   - `YOUTUBE_CHANNELS` — comma-separated handles or names, e.g. `@MKBHD,@ChannelName`

3. Run:

   ```bash
   python main.py
   ```

  **Single-video mode** (no channel discovery): pass one or more video URLs/IDs to process them (transcript → summarize → Telegram). Only `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` are required.

   ```bash
   python main.py --video -jRur5z6TPk
   python main.py --video "https://www.youtube.com/watch?v=-jRur5z6TPk"
   python main.py --video -jRur5z6TPk https://youtu.be/abcdEFGhijk
   ```

## Behaviour

- **Discovery**: If `YOUTUBE_API_KEY` is set, the app uses YouTube Data API v3 to list today’s uploads for each channel. Otherwise it uses Brave Video Search (set `BRAVE_API_KEY`). At least one is required.
- **Transcripts**: [youtube-transcript-api](https://pypi.org/project/youtube-transcript-api/) is tried first. If the video has no captions and `TRANSCRIPT_FALLBACK=whisper`, the app uses **yt-dlp** + **OpenAI Whisper** (requires `ffmpeg`).
- **Summarization**: Transcript is sent to Gemini; summary can include pipe tables (| col | col |).
- **Telegram**: One message per video (title, link, summary). Messages over 4096 characters are split. Idempotency: `processed_videos.json` stores processed video IDs.
- **Saved outputs**:
  - **Naming**: saved using `channel_YYYY_MM_DD.(txt|md)` where the date is the **video upload date** (`publishedAt`).
    - Getting upload time requires `YOUTUBE_API_KEY`; if it’s not set, the script falls back to today’s UTC date.
  - **Transcripts**: `transcripts/<channel>_YYYY_MM_DD.txt` (appended per video)
  - **Summaries**: `summaries/<channel>_YYYY_MM_DD.md` (appended per video)

## Optional

- **YouTube Data API**: Set `YOUTUBE_API_KEY` (enable YouTube Data API v3 in Google Cloud) so discovery uses the channel’s real uploads instead of Brave search.
- **Whisper fallback**: Set `TRANSCRIPT_FALLBACK=whisper` and install `yt-dlp`, `openai-whisper`, and **ffmpeg**. Optional: `WHISPER_MODEL=tiny` or `WHISPER_MODEL=small`.
- **Gemini model**: Set `GEMINI_MODEL` (e.g. `gemini-1.5-pro`) in `.env`.
- **Scheduling**: Run `python main.py` via cron or a scheduler (e.g. once per day).
