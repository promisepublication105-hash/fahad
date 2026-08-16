# Bangla Dub Studio

Upload a video whose speech is in English and get back a version dubbed into
Bangla — with the mouth movements re-synced to match, when a lip-sync
provider is configured.

## How it works

```
video upload
   │
   ▼
1. extract audio                      (ffmpeg)
2. transcribe English speech          (OpenAI Whisper) → timestamped segments
3. translate each segment to Bangla   (OpenAI chat model)
4. synthesize Bangla speech           (Google Cloud Text-to-Speech, bn-IN)
5. time-stretch each clip to fit      (ffmpeg atempo) and lay it back onto
   its original time slot                a silent track the length of the video
6. mux the new audio into the video   (ffmpeg)
7. (optional) lip-sync                (sync.so) → mouth movement matches the
                                          new Bangla audio
```

Each stage lives in its own file under `backend/services/`, so you can swap
any provider out later without touching the rest of the pipeline.

**Without any API keys**, the app still runs, but every step that calls an
external API will fail with a clear error telling you which key is missing.
**Without a lip-sync key specifically**, everything else still works — you
get a fully Bangla-dubbed video, just with the original English lip
movements (which is a completely reasonable app on its own; lip-sync is a
polish layer on top).

## Setup

**Prerequisites**
- Python 3.10+
- `ffmpeg` installed and on your `PATH` (`apt install ffmpeg` / `brew install ffmpeg`)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env — see below for what each key does and where to get it
```

**Run it:**

```bash
uvicorn backend.main:app --reload --port 8000
```

Open http://localhost:8000, upload a video, and watch it progress through
the pipeline.

## API keys — what each one unlocks

| Key | Unlocks | Get it from |
|---|---|---|
| `OPENAI_API_KEY` | Transcription (step 2) + translation (step 3) | https://platform.openai.com/api-keys |
| `GOOGLE_APPLICATION_CREDENTIALS` | Bangla voice generation (step 4) | Google Cloud Console → enable "Cloud Text-to-Speech API" → create a service account → download its JSON key |
| `SYNC_API_KEY` + `PUBLIC_BASE_URL` | Lip-sync (step 7, optional) | https://sync.so — `PUBLIC_BASE_URL` is your server's own public URL (e.g. an `ngrok http 8000` tunnel while developing), since sync.so needs to fetch your video/audio files over HTTP |

You don't need all three to try the app — get `OPENAI_API_KEY` and
`GOOGLE_APPLICATION_CREDENTIALS` working first; that alone gives you a
working English → Bangla dub. Add `SYNC_API_KEY`/`PUBLIC_BASE_URL` later for
lip-sync.

## Project layout

```
backend/
  main.py            FastAPI app: upload endpoint, job status/polling, download
  pipeline.py         orchestrates the 7 steps above for one job
  config.py            all settings, read from environment variables
  models.py, store.py  in-memory job tracking
  services/
    transcribe.py       OpenAI Whisper
    translate.py         OpenAI chat model
    tts.py                 Google Cloud TTS
    audio_align.py          time-stretch + place segments on the timeline
    mux.py                    ffmpeg audio replacement
    lipsync.py                  sync.so integration (optional)
static/                the browser UI (upload, progress bar, preview/download)
```

## Known limitations / natural next steps

- **Job state is in-memory** — restarting the server loses in-flight job
  status (the files on disk are untouched though). Swap `backend/store.py`
  for SQLite if you need that to survive restarts.
- **Translation is one API call per line** — fine for a few-minute video,
  slow/costlier for a long one. Batch multiple lines per call if you need to
  scale this up.
- **Lip-sync requires a public URL.** Great once deployed; for local dev,
  run something like `ngrok http 8000` and put that URL in
  `PUBLIC_BASE_URL`.
- **500 MB upload cap** (`MAX_UPLOAD_BYTES` in `backend/main.py`) — raise it
  if you need to handle longer/larger videos.
- Currently dubs everything into Bangla (`bn-IN` voice); the target language
  is already a parameter end-to-end (`target_lang`) if you want to extend
  the UI to support more languages later.
