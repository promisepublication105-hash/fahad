"""Step 3: synthesize each translated line as Bangla speech.

Uses Google Cloud Text-to-Speech, which has good WaveNet/Neural2 Bangla
(bn-IN) voices. Auth is via a service-account JSON key referenced by the
GOOGLE_APPLICATION_CREDENTIALS environment variable (the google-cloud
library reads that automatically — see .env.example).
"""
import os

from ..config import settings


def synthesize(text: str) -> bytes:
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set. Point it at a Google "
            "Cloud service-account JSON key with Text-to-Speech access "
            "(see .env.example)."
        )

    # Imported lazily so the whole app doesn't hard-fail at startup if the
    # optional google-cloud-texttospeech package isn't installed yet.
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    input_ = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code=settings.tts_language_code,
        name=settings.tts_voice_name,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=24000,
    )
    resp = client.synthesize_speech(input=input_, voice=voice, audio_config=audio_config)
    return resp.audio_content
