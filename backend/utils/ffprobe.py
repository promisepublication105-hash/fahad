import json
import subprocess


def get_duration_ms(path: str) -> int:
    """Return a media file's duration in milliseconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", path,
        ],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return int(float(data["format"]["duration"]) * 1000)
