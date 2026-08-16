"""Step 6 (optional): re-sync the video's mouth movements to the new audio.

Uses sync.so's hosted lip-sync API. This step is entirely optional — if
SYNC_API_KEY / PUBLIC_BASE_URL aren't configured, the pipeline just skips it
and ships the Bangla-dubbed video with the original (English) lip movements.

sync.so needs to fetch your video/audio over HTTP(S), so your server must be
publicly reachable (a real domain in production, or an ngrok/cloudflared
tunnel during local development) for this step to work.

NOTE: this talks to a third-party REST API whose exact field names can
change over time. If generation requests start failing, check the current
schema at https://sync.so/docs/api-reference before assuming the pipeline
code is wrong.
"""
import time
from typing import Optional

import requests

from ..config import settings

API_BASE = "https://api.sync.so/v2"


def is_configured() -> bool:
    return bool(settings.sync_api_key and settings.public_base_url)


def apply(video_url: str, audio_url: str) -> Optional[str]:
    """Submit a lip-sync generation job and poll until it completes.
    Returns the output video's URL, or raises on failure/timeout.
    """
    headers = {"x-api-key": settings.sync_api_key, "Content-Type": "application/json"}
    payload = {
        "model": settings.sync_model,
        "input": [
            {"type": "video", "url": video_url},
            {"type": "audio", "url": audio_url},
        ],
    }
    resp = requests.post(f"{API_BASE}/generate", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    job_id = resp.json()["id"]

    for _ in range(120):  # poll for up to ~20 minutes
        time.sleep(10)
        status_resp = requests.get(f"{API_BASE}/generate/{job_id}", headers=headers, timeout=30)
        status_resp.raise_for_status()
        data = status_resp.json()
        status = str(data.get("status", "")).upper()
        if status == "COMPLETED":
            return data.get("outputUrl") or data.get("output_url") or data.get("url")
        if status in ("FAILED", "CANCELED", "CANCELLED"):
            raise RuntimeError(f"sync.so generation failed: {data}")

    raise TimeoutError("sync.so generation timed out")


def download(url: str, out_path: str) -> str:
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return out_path
