"""Orchestrates one "product ad" job: photos + Bangla lines -> MP4 commercial."""
import io
import os
from typing import List, Optional

from PIL import Image, ImageOps

from . import store
from .config import settings
from .services import ad_render, tts


def _voice_provider() -> Optional[str]:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return "google"
    if settings.openai_api_key:
        return "openai"
    return None


def _synthesize(text: str, provider: str):
    """Return a pydub AudioSegment of `text` spoken in Bangla."""
    from pydub import AudioSegment

    if provider == "google":
        wav = tts.synthesize(text)  # LINEAR16 WAV bytes
        return AudioSegment.from_file(io.BytesIO(wav), format="wav")

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.audio.speech.create(
        model=settings.ad_openai_tts_model,
        voice=settings.ad_openai_tts_voice,
        input=text,
        instructions="Speak in natural Bangla (Bengali), warm and upbeat, "
                     "like a friendly TV commercial voiceover.",
        response_format="wav",
    )
    return AudioSegment.from_file(io.BytesIO(resp.read()), format="wav")


def run_ad_pipeline(job_id: str, image_paths: List[str], product_name: str,
                    lines: List[str], tagline: str, cta: str, contact: str,
                    brand_color: str, aspect: str, voiceover: bool,
                    music_path: Optional[str], builtin_music: bool) -> None:
    job = store.get(job_id)
    if job is None:
        return
    job_dir = os.path.dirname(image_paths[0])

    try:
        job.status, job.stage, job.progress = "processing", "preparing photos", 3
        store.save(job)
        images = []
        for p in image_paths:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((2400, 2400))
                images.append(im.convert("RGB"))

        voice_clips, end_voice = [], None
        if voiceover:
            provider = _voice_provider()
            if provider is None:
                job.notes.append(
                    "Voiceover skipped: set GOOGLE_APPLICATION_CREDENTIALS (Google "
                    "TTS) or OPENAI_API_KEY in .env to get a Bangla voice. The ad "
                    "has captions and music only."
                )
            else:
                job.stage, job.progress = f"recording Bangla voiceover ({provider})", 8
                store.save(job)
                try:
                    for i, line in enumerate(lines):
                        voice_clips.append(_synthesize(line, provider))
                        job.progress = 8 + int(17 * (i + 1) / (len(lines) + 1))
                        store.save(job)
                    closing = " ".join(x for x in (product_name, tagline, cta) if x)
                    end_voice = _synthesize(closing, provider)
                except Exception as e:  # noqa: BLE001 - still deliver a silent-voice ad
                    voice_clips, end_voice = [], None
                    job.notes.append(f"Voiceover failed, made the ad without it: {e}")

        job.stage, job.progress = "rendering video", 25
        store.save(job)
        spec = ad_render.AdSpec(
            images=images, product_name=product_name, lines=lines,
            tagline=tagline, cta=cta or "এখনই অর্ডার করুন", contact=contact,
            brand_color=ad_render.parse_color(brand_color), aspect=aspect,
            voice_clips=voice_clips, end_voice=end_voice,
        )

        def on_progress(frac: float) -> None:
            job.progress = 25 + int(73 * frac)
            store.save(job)

        out_name = "ad.mp4"
        ad_render.render_ad(spec, os.path.join(job_dir, out_name), job_dir,
                            music_path, builtin_music, on_progress)

        job.status, job.stage, job.progress = "done", "complete", 100
        job.result_filename = out_name
        store.save(job)
    except Exception as e:  # noqa: BLE001 - surface any failure to the UI
        job.status, job.error = "error", str(e)
        store.save(job)
