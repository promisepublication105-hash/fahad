"""Step 2: translate each English segment into natural, spoken Bangla.

Each line is translated with its target speaking duration in mind so the
Bangla text isn't wildly longer/shorter than the slot it needs to fill —
this keeps the later time-stretch step from having to work too hard.
"""
from typing import List

from openai import OpenAI

from ..config import settings

LANGUAGE_NAMES = {
    "bn": "Bangla (Bengali)",
}


def translate_segments(segments: List[dict], target_lang: str = "bn") -> List[dict]:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your .env file to enable "
            "translation (see .env.example)."
        )

    client = OpenAI(api_key=settings.openai_api_key)
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)

    out = []
    for seg in segments:
        duration = max(seg["end"] - seg["start"], 0.5)
        prompt = (
            f"Translate the following English line into natural, spoken "
            f"{lang_name}, as a dubbing script line (not a literal word-for-word "
            f"translation). It should be speakable out loud in roughly "
            f"{duration:.1f} seconds — keep it concise if the source is short. "
            f"Return ONLY the translated line, no quotes, no notes.\n\n"
            f"English: {seg['text']}"
        )
        resp = client.chat.completions.create(
            model=settings.translation_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        translated = resp.choices[0].message.content.strip()
        out.append({**seg, "translated_text": translated})
    return out
