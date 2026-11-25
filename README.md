# Bangla Dub Studio

Two tools in one app:

1. **Product ad maker** — upload product photos, write (or let AI write) a
   few Bangla lines, and get a short social-media commercial: animated
   product shots, Bangla captions, Bangla voiceover, background music and a
   closing card with your call-to-action. Exports 9:16 (Reels/TikTok), 1:1
   (feed) or 16:9 (YouTube).
2. **Video dubbing** — upload a video whose speech is in English and get back
   a version dubbed into Bangla, with the mouth movements re-synced to match
   when a lip-sync provider is configured.

## Product ad maker

```
product photos + product name + scene lines (Bangla)
   │
   ▼
1. (optional) AI writes the script     (OpenAI chat model) → hook, product,
                                          benefits, result + tagline + CTA
2. Bangla voiceover per line           (Google Cloud TTS, else OpenAI TTS)
3. render each scene                    (Pillow): photo card with slow
                                          push-in over a blurred, brand-tinted
                                          background; caption slides up
4. closing brand card                   product, name, tagline, CTA button,
                                          contact line
5. cross-fades, music + voice mix,      (ffmpeg, pydub) → MP4 (H.264/AAC)
   encode
```

Scene length follows the voiceover, so each line gets enough time on
screen. With no API keys at all it still works: you type the lines yourself
and get a captioned ad with soft background music, without a voiceover.

Tips for good results:
- Use clean, well-lit product photos (plain or lifestyle backgrounds both
  work). Upload 3–5 different angles so scenes don't repeat.
- Keep each line short (6–12 words). One idea per scene.
- Pick a brand colour that matches your packaging; it tints the background
  and the closing card.
- Upload your own music to replace the built-in soft pad.

Bangla text is drawn with the bundled Hind Siliguri font
(`assets/fonts/`, SIL Open Font License), so conjuncts render correctly.

## Video dubbing — how it works

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
| `OPENAI_API_KEY` | Dubbing: transcription + translation. Ads: AI script writer, and Bangla voiceover if Google TTS isn't set | https://platform.openai.com/api-keys |
| `GOOGLE_APPLICATION_CREDENTIALS` | Bangla voice for dubbing and for ads (preferred ad voice) | Google Cloud Console → enable "Cloud Text-to-Speech API" → create a service account → download its JSON key |
| `SYNC_API_KEY` + `PUBLIC_BASE_URL` | Lip-sync (step 7, optional) | https://sync.so — `PUBLIC_BASE_URL` is your server's own public URL (e.g. an `ngrok http 8000` tunnel while developing), since sync.so needs to fetch your video/audio files over HTTP |

You don't need all three to try the app — get `OPENAI_API_KEY` and
`GOOGLE_APPLICATION_CREDENTIALS` working first; that alone gives you a
working English → Bangla dub. Add `SYNC_API_KEY`/`PUBLIC_BASE_URL` later for
lip-sync.

## Project layout

```
assets/fonts/        Hind Siliguri (Bangla + Latin) used for ad captions
backend/
  main.py            FastAPI app: upload endpoints, job status/polling, download
  pipeline.py         orchestrates the dubbing steps for one job
  ad_pipeline.py      orchestrates a product-ad job (voiceover + render)
  config.py            all settings, read from environment variables
  models.py, store.py  in-memory job tracking
  services/
    transcribe.py       OpenAI Whisper
    translate.py         OpenAI chat model
    tts.py                 Google Cloud TTS
    audio_align.py          time-stretch + place segments on the timeline
    mux.py                    ffmpeg audio replacement
    lipsync.py                  sync.so integration (optional)
    ad_script.py                AI-written Bangla ad script (OpenAI)
    ad_render.py                scene animation, end card, music, encode
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
