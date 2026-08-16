"""Orchestrates the full upload -> Bangla-dubbed-video pipeline for one job."""
import os
import subprocess

from . import store
from .config import settings
from .services import audio_align, lipsync, mux, transcribe, translate, tts
from .utils.ffprobe import get_duration_ms


def _extract_audio(video_path: str, out_path: str) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            out_path,
        ],
        check=True, capture_output=True,
    )


def run_pipeline(job_id: str, video_path: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    job_dir = os.path.dirname(video_path)

    try:
        job.status, job.stage, job.progress = "processing", "extracting audio", 5
        store.save(job)
        audio_path = os.path.join(job_dir, "original_audio.wav")
        _extract_audio(video_path, audio_path)

        job.stage, job.progress = "transcribing English speech", 15
        store.save(job)
        segments, _detected_lang = transcribe.transcribe(audio_path)
        if not segments:
            raise RuntimeError("No speech was detected in the uploaded video.")

        job.stage, job.progress = "translating to Bangla", 30
        store.save(job)
        segments = translate.translate_segments(segments, job.target_lang)

        job.stage, job.progress = "generating Bangla voice", 50
        store.save(job)
        for seg in segments:
            seg["audio_bytes"] = tts.synthesize(seg["translated_text"])

        job.stage, job.progress = "aligning timing to video", 65
        store.save(job)
        total_ms = get_duration_ms(video_path)
        track = audio_align.build_track(segments, total_ms)
        dubbed_audio_path = os.path.join(job_dir, "dubbed_audio.wav")
        track.export(dubbed_audio_path, format="wav")

        job.stage, job.progress = "merging Bangla audio into video", 80
        store.save(job)
        muxed_path = os.path.join(job_dir, "dubbed_video.mp4")
        mux.replace_audio(video_path, dubbed_audio_path, muxed_path)

        final_filename = "dubbed_video.mp4"
        if lipsync.is_configured():
            job.stage, job.progress = "syncing lip movements", 90
            store.save(job)
            try:
                video_url = f"{settings.public_base_url}/files/{job_id}/dubbed_video.mp4"
                audio_url = f"{settings.public_base_url}/files/{job_id}/dubbed_audio.wav"
                output_url = lipsync.apply(video_url, audio_url)
                if output_url:
                    lipsynced_path = os.path.join(job_dir, "lipsynced_video.mp4")
                    lipsync.download(output_url, lipsynced_path)
                    final_filename = "lipsynced_video.mp4"
                else:
                    job.notes.append(
                        "Lip-sync returned no output; shipped voice-only dub instead."
                    )
            except Exception as e:  # noqa: BLE001 - degrade gracefully, don't fail the whole job
                job.notes.append(f"Lip-sync step failed, shipped voice-only dub instead: {e}")
        else:
            job.notes.append(
                "Lip-sync skipped: set SYNC_API_KEY and PUBLIC_BASE_URL in .env to enable "
                "mouth-movement syncing. The video below has the new Bangla audio but the "
                "original English lip movements."
            )

        job.status, job.stage, job.progress = "done", "complete", 100
        job.result_filename = final_filename
        store.save(job)

    except Exception as e:  # noqa: BLE001 - surface any failure to the UI
        job.status, job.error = "error", str(e)
        store.save(job)
