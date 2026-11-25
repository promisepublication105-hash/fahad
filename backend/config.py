"""Central place all pipeline settings are read from.

Everything is driven by environment variables (loaded from a local .env
file by backend/main.py) so you can plug in real API keys without touching
any code. See .env.example for the full list with explanations.
"""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    # --- OpenAI: used for transcription (Whisper) and translation (chat model)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    transcription_model: str = os.getenv("TRANSCRIPTION_MODEL", "whisper-1")
    translation_model: str = os.getenv("TRANSLATION_MODEL", "gpt-4o-mini")

    # --- Google Cloud Text-to-Speech: used to generate the Bangla voice
    # Auth is via GOOGLE_APPLICATION_CREDENTIALS pointing at a service
    # account JSON key (the Google client library reads that env var itself).
    tts_language_code: str = os.getenv("TTS_LANGUAGE_CODE", "bn-IN")
    tts_voice_name: str = os.getenv("TTS_VOICE_NAME", "bn-IN-Wavenet-A")

    # --- sync.so: optional lip-sync pass. Without this, the app still
    # produces a Bangla-dubbed video, just with the original English lip
    # movements.
    sync_api_key: str = os.getenv("SYNC_API_KEY", "")
    sync_model: str = os.getenv("SYNC_MODEL", "lipsync-2")
    # A public HTTPS URL your running server is reachable at, e.g. an ngrok
    # tunnel in dev or your real domain in production. sync.so needs to be
    # able to fetch the dubbed video/audio it lip-syncs.
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")

    # --- Product-ad maker: Bangla voiceover fallback when Google TTS isn't
    # configured (OpenAI's TTS speaks Bangla reasonably well).
    ad_openai_tts_model: str = os.getenv("AD_OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    ad_openai_tts_voice: str = os.getenv("AD_OPENAI_TTS_VOICE", "nova")

    storage_dir: str = os.getenv("STORAGE_DIR", "storage")


settings = Settings()
