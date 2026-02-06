FROM python:3.12-slim

WORKDIR /app

# System deps:
# - ffmpeg: required when TRANSCRIPT_FALLBACK=whisper
# - ca-certificates: TLS
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -U pip \
  && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Persist outputs by mounting a volume and setting APP_DATA_DIR=/data.
ENV APP_DATA_DIR=/data

ENTRYPOINT ["python", "main.py"]
