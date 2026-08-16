"""Step 1: turn the video's English speech into timestamped text segments.

Uses OpenAI's Whisper transcription API. Segment-level timestamps are what
let us later place each translated line back at the right spot in the video.
"""
from typing import List, Tuple

from openai import OpenAI

from ..config import settings


def transcribe(audio_path: str) -> Tuple[List[dict], str]:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your .env file to enable "
            "transcription (see .env.example)."
        )

    client = OpenAI(api_key=settings.openai_api_key)
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=settings.transcription_model,
            file=f,
            response_format="verbose_json",
        )

    raw_segments = getattr(resp, "segments", None) or []
    segments = []
    for s in raw_segments:
        # Handle both the pydantic object and a plain-dict fallback, since
        # SDK versions have varied in how they expose this.
        start = getattr(s, "start", None) if not isinstance(s, dict) else s.get("start")
        end = getattr(s, "end", None) if not isinstance(s, dict) else s.get("end")
        text = getattr(s, "text", None) if not isinstance(s, dict) else s.get("text")
        text = (text or "").strip()
        if text and start is not None and end is not None:
            segments.append({"start": float(start), "end": float(end), "text": text})

    language = getattr(resp, "language", "en")
    return segments, language
