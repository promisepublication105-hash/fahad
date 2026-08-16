"""Step 5: replace the video's original audio track with the dubbed one."""
import subprocess


def replace_audio(video_path: str, audio_path: str, output_path: str) -> str:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ],
        check=True, capture_output=True,
    )
    return output_path
