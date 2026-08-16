"""Step 4: fit each synthesized Bangla clip into its original time slot.

Google TTS won't naturally speak a line in exactly the same duration as the
original English line, so we time-stretch/compress each clip (via ffmpeg's
atempo filter) to match, then lay all clips onto a silent track at their
original start times.
"""
import io
import os
import subprocess
import tempfile
from typing import List

from pydub import AudioSegment


def _atempo_chain(ratio: float) -> str:
    """ffmpeg's atempo filter only accepts 0.5-2.0 per instance; chain
    multiple instances together to reach more extreme ratios."""
    filters = []
    r = ratio
    while r > 2.0:
        filters.append("atempo=2.0")
        r /= 2.0
    while r < 0.5:
        filters.append("atempo=0.5")
        r /= 0.5
    filters.append(f"atempo={r:.3f}")
    return ",".join(filters)


def _time_stretch(clip: AudioSegment, target_ms: int) -> AudioSegment:
    current_ms = len(clip)
    if target_ms <= 0:
        return AudioSegment.silent(duration=0)
    if current_ms <= 0:
        return AudioSegment.silent(duration=target_ms)

    ratio = current_ms / target_ms  # >1 = clip is too long, needs speeding up
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "in.wav")
        out_path = os.path.join(tmp, "out.wav")
        clip.export(in_path, format="wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", in_path, "-filter:a", _atempo_chain(ratio), out_path],
            check=True, capture_output=True,
        )
        stretched = AudioSegment.from_file(out_path)

    # Exact-fit safety net: pad with silence or trim to the target slot.
    if len(stretched) < target_ms:
        stretched += AudioSegment.silent(duration=target_ms - len(stretched))
    else:
        stretched = stretched[:target_ms]
    return stretched


def build_track(segments_with_audio: List[dict], total_duration_ms: int) -> AudioSegment:
    base = AudioSegment.silent(duration=total_duration_ms)
    for seg in segments_with_audio:
        target_ms = int(round((seg["end"] - seg["start"]) * 1000))
        clip = AudioSegment.from_file(io.BytesIO(seg["audio_bytes"]))
        clip = _time_stretch(clip, target_ms)
        start_ms = int(round(seg["start"] * 1000))
        base = base.overlay(clip, position=start_ms)
    return base
