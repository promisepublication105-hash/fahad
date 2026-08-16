"""In-memory job registry.

Good enough for a single-process MVP. If you outgrow it (multiple worker
processes, restarts losing job state), swap this for a small SQLite table —
Job.to_dict()/from a row is already the right shape for that.
"""
import threading
from typing import Dict, Optional

from .models import Job

_JOBS: Dict[str, Job] = {}
_LOCK = threading.Lock()


def save(job: Job) -> None:
    with _LOCK:
        _JOBS[job.id] = job


def get(job_id: str) -> Optional[Job]:
    with _LOCK:
        return _JOBS.get(job_id)
