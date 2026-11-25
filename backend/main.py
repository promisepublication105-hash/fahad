import os
import shutil
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from . import store  # noqa: E402
from .config import settings  # noqa: E402
from .models import Job  # noqa: E402
from .ad_pipeline import run_ad_pipeline  # noqa: E402
from .pipeline import run_pipeline  # noqa: E402
from .services import ad_render, ad_script  # noqa: E402

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
    name = f"bangla_ad_{job_id}.mp4" if job.kind == "ad" else f"bangla_{job.filename}"
    return FileResponse(path, media_type="video/mp4", filename=name)


# --------------------------------------------------------------------------
# Product-ad maker
# --------------------------------------------------------------------------

MAX_AD_IMAGES = 8
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_MUSIC_BYTES = 30 * 1024 * 1024


async def _save_upload(upload: UploadFile, path: str, limit: int) -> None:
    size = 0
    with open(path, "wb") as out:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, f"{upload.filename} is too large.")
            out.write(chunk)


@app.post("/api/ads/script")
async def ad_script_endpoint(
    product_name: str = Form(...),
    description: str = Form(""),
    num_scenes: int = Form(4),
):
    try:
        return ad_script.write_script(product_name, description, num_scenes)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


@app.post("/api/ads")
async def create_ad(
    background_tasks: BackgroundTasks,
    images: List[UploadFile] = File(...),
    product_name: str = Form(...),
    scenes: str = Form(...),               # one line per scene
    tagline: str = Form(""),
    cta: str = Form("এখনই অর্ডার করুন"),
    contact: str = Form(""),
    brand_color: str = Form("#c0587a"),
    aspect: str = Form("9:16"),
    voiceover: bool = Form(True),
    builtin_music: bool = Form(True),
    music: Optional[UploadFile] = File(None),
):
    lines = [ln.strip() for ln in scenes.splitlines() if ln.strip()]
    if not product_name.strip():
        raise HTTPException(400, "Product name is required.")
    if not lines:
        raise HTTPException(400, "Write at least one scene line.")
    if len(lines) > 10:
        raise HTTPException(400, "Use at most 10 scene lines.")
    if not images or len(images) > MAX_AD_IMAGES:
        raise HTTPException(400, f"Upload 1-{MAX_AD_IMAGES} product photos.")
    if aspect not in ad_render.ASPECTS:
        raise HTTPException(400, f"aspect must be one of {list(ad_render.ASPECTS)}")

    job = Job(kind="ad", filename=f"{product_name.strip()} ad")
    job_dir = os.path.join(settings.storage_dir, job.id)
    os.makedirs(job_dir, exist_ok=True)
    try:
        image_paths = []
        for i, img in enumerate(images):
            ext = os.path.splitext(img.filename or "")[1].lower() or ".jpg"
            path = os.path.join(job_dir, f"photo_{i}{ext}")
            await _save_upload(img, path, MAX_IMAGE_BYTES)
            image_paths.append(path)

        from PIL import Image  # validate the photos before queueing the job
        for p in image_paths:
            try:
                with Image.open(p) as im:
                    im.verify()
            except Exception:
                raise HTTPException(400, f"{os.path.basename(p)} isn't a readable image.")

        music_path = None
        if music is not None and music.filename:
            ext = os.path.splitext(music.filename)[1].lower() or ".mp3"
            music_path = os.path.join(job_dir, f"music_upload{ext}")
            await _save_upload(music, music_path, MAX_MUSIC_BYTES)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    store.save(job)
    background_tasks.add_task(
        run_ad_pipeline, job.id, image_paths, product_name.strip(), lines,
        tagline.strip(), cta.strip(), contact.strip(), brand_color, aspect,
        voiceover, music_path, builtin_music,
    )
    return job.to_dict()


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
