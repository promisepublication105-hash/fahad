import os
import shutil

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from . import store  # noqa: E402
from .config import settings  # noqa: E402
from .models import Job  # noqa: E402
from .pipeline import run_pipeline  # noqa: E402

app = FastAPI(title="Bangla Dub Studio")

os.makedirs(settings.storage_dir, exist_ok=True)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


@app.post("/api/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_lang: str = Form("bn"),
):
    job = Job(filename=file.filename or "video.mp4", target_lang=target_lang)
    job_dir = os.path.join(settings.storage_dir, job.id)
    os.makedirs(job_dir, exist_ok=True)

    ext = os.path.splitext(job.filename)[1] or ".mp4"
    input_path = os.path.join(job_dir, f"input{ext}")

    size = 0
    with open(input_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(413, "File too large (limit 500 MB).")
            out.write(chunk)

    store.save(job)
    background_tasks.add_task(run_pipeline, job.id, input_path)
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str):
    job = store.get(job_id)
    if not job or not job.result_filename:
        raise HTTPException(404, "Result not ready yet.")
    path = os.path.join(settings.storage_dir, job_id, job.result_filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Result file missing.")
    return FileResponse(path, media_type="video/mp4", filename=f"bangla_{job.filename}")


@app.get("/files/{job_id}/{filename}")
async def get_file(job_id: str, filename: str):
    """Serves job files over HTTP so the (optional) lip-sync provider can
    fetch them. Only used when SYNC_API_KEY/PUBLIC_BASE_URL are configured."""
    safe_name = os.path.basename(filename)
    path = os.path.join(settings.storage_dir, job_id, safe_name)
    if not os.path.exists(path):
        raise HTTPException(404, "Not found.")
    return FileResponse(path)


# Serve the simple web UI. Mounted last so it doesn't shadow the /api and
# /files routes above.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
