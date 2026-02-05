# YouTube Channel Crawler + Summarizer + Telegram Bot

Crawls configured YouTube channels for new uploads, fetches transcripts, summarizes with Gemini, and sends summaries to Telegram.

## Requirements

- Python 3.10+
- API keys: Brave Search or YouTube Data API, Google Gemini, Telegram Bot

## Setup

1. Clone or copy this project, then create a virtualenv and install dependencies.

   **Quick install script (recommended):**

   ```bash
   chmod +x install.sh
   ./install.sh
   ```

   **Recommended (pinned, same versions as the repo author):**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -U pip
   pip install -r requirements.lock.txt
   ```

   **Alternative (unpinned):**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -U pip
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your keys:

   - `YOUTUBE_API_KEY` — (recommended) YouTube Data API v3 key (enables correct channel discovery + upload time `publishedAt`)
   - `BRAVE_API_KEY` — Brave Search API key (used only if `YOUTUBE_API_KEY` is not set)
   - `GEMINI_API_KEY` — Google AI / Gemini API key
   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `TELEGRAM_CHAT_ID` — message your bot, then call `getUpdates` or use [@userinfobot](https://t.me/userinfobot)
   - `YOUTUBE_CHANNELS` — comma-separated handles or names, e.g. `@MKBHD,@ChannelName`

3. Run:

   ```bash
   python main.py
   ```

  **Single-video mode** (no channel discovery): pass one or more video URLs/IDs to process them (transcript → summarize → Telegram).
  - Only `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` are required.
  - If `YOUTUBE_API_KEY` is set, filenames use the real upload date (`publishedAt`) and the channel name is more accurate.

   ```bash
   python main.py --video -jRur5z6TPk
   python main.py --video "https://www.youtube.com/watch?v=-jRur5z6TPk"
   python main.py --video -jRur5z6TPk https://youtu.be/abcdEFGhijk
   python main.py --video -jRur5z6TPk,abcdEFGhijk
   ```

## Behaviour

- **Discovery**:
  - If `YOUTUBE_API_KEY` is set, the app uses YouTube Data API v3 to list **recent uploads** per channel (default lookback: last 24 hours).
  - Otherwise it uses Brave Video Search (set `BRAVE_API_KEY`).
  - At least one of `YOUTUBE_API_KEY` or `BRAVE_API_KEY` is required for **channel mode**.
- **Transcripts**: [youtube-transcript-api](https://pypi.org/project/youtube-transcript-api/) is tried first. If the video has no captions and `TRANSCRIPT_FALLBACK=whisper`, the app uses **yt-dlp** + **OpenAI Whisper** (requires `ffmpeg`).
- **Summarization**: Transcript is sent to Gemini; summary can include pipe tables (| col | col |).
- **Telegram**: One message per video (title, link, summary). Messages over 4096 characters are split. Idempotency: `processed_videos.json` stores processed video IDs.
- **Saved outputs**:
  - **Naming**: saved using `channel_YYYY_MM_DD.(txt|md)` where the date is the **video upload date** (`publishedAt`).
    - Getting upload time requires `YOUTUBE_API_KEY`; if it’s not set, the script falls back to today’s UTC date.
  - **Transcripts**: `transcripts/<channel>_YYYY_MM_DD.txt` (appended per video)
  - **Summaries**: `summaries/<channel>_YYYY_MM_DD.md` (appended per video)
  - **HTMLs (optional)**: `htmls/<channel>_YYYY-MM-DD.html` (sent to Telegram when enabled)
  - **Binary note**: when running the PyInstaller binary, these files are read/written relative to the **executable directory** (same folder as `dist/ai-agent`).

## Repo structure

```text
ai-agent/
  main.py                 # CLI entrypoint; orchestrates fetch → summarize → save → Telegram
  transcript.py            # Transcript fetch (YouTube captions + optional Whisper fallback)
  summarize.py             # Gemini summarization prompt + API call
  html_export.py           # Convert summary markdown-ish text → styled HTML (real tables)
  youtube_channel.py       # YouTube Data API discovery (preferred when YOUTUBE_API_KEY is set)
  brave_search.py          # Brave Search discovery (fallback when no YOUTUBE_API_KEY)
  telegram_send.py         # Telegram send message + sendDocument (HTML upload)
  processed_videos.json    # Idempotency store (already-processed video IDs)

  install.sh               # Create .venv and install from requirements.lock.txt
  build_binary.sh          # Build a standalone macOS executable via PyInstaller
  requirements.txt         # Minimal dependency list (unpinned)
  requirements.lock.txt    # Fully pinned dependency lock (recommended)
  .env.example             # Environment variable template

  transcripts/             # Saved transcripts (appended per video)
  summaries/               # Saved Markdown summaries (appended per video)
  htmls/                   # Generated HTML summaries (one per day/channel)
```

## Optional

- **YouTube Data API**: Set `YOUTUBE_API_KEY` (enable YouTube Data API v3 in Google Cloud) so discovery uses the channel’s real uploads instead of Brave search.
- **Whisper fallback**: Set `TRANSCRIPT_FALLBACK=whisper` and install `yt-dlp`, `openai-whisper`, and **ffmpeg**. Optional: `WHISPER_MODEL=tiny` or `WHISPER_MODEL=small`.
- **Send per-video HTMLs to Telegram**: Set `TELEGRAM_SEND_HTML=1`. This exports the summary to a self-contained `.html` file with real HTML tables (saved under `./htmls/`), then uploads it to Telegram as a document.
- **Send text summary message**: Controlled by `TELEGRAM_SEND_SUMMARY` (default `1`). If `TELEGRAM_SEND_HTML=1`, the default behavior is to send **only the HTML file** (no text summary).
- **Gemini model**: Set `GEMINI_MODEL` (e.g. `gemini-1.5-pro`) in `.env`.
- **Scheduling**: Run `python main.py` via cron or a scheduler (e.g. once per day).

## Build a standalone binary (macOS)

This project can be packaged into a single executable using PyInstaller.

```bash
chmod +x build_binary.sh
./build_binary.sh
```

- Output: `dist/<name>` (default: `dist/ai-agent`)
- Run:

```bash
./dist/ai-agent --help
./dist/ai-agent --video -jRur5z6TPk
```

### Binary build options

PyInstaller builds are **not cross-platform** (build on each OS you want to support). On macOS, you can choose target arch.

- `APP_NAME` (default: `ai-agent`)
- `NAME_WITH_PLATFORM=1`: name output like `ai-agent-darwin-arm64`
- `TARGET_ARCH=arm64|x86_64|universal2` (macOS only)

Examples:

```bash
NAME_WITH_PLATFORM=1 ./build_binary.sh
TARGET_ARCH=universal2 NAME_WITH_PLATFORM=1 ./build_binary.sh
```

## Updating the lock file (maintainers)

If you add/remove dependencies, regenerate the lock file from your working venv:

```bash
source .venv/bin/activate
pip freeze > requirements.lock.txt
```
