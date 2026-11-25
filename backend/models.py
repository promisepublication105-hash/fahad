from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
import uuid


@dataclass
class Job:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    kind: str = "dub"               # dub | ad
    filename: str = ""
    target_lang: str = "bn"
    status: str = "queued"          # queued | processing | done | error
    stage: str = ""                 # human-readable current step
    progress: int = 0               # 0-100
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None
    result_filename: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "filename": self.filename,
            "target_lang": self.target_lang,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "notes": self.notes,
            "error": self.error,
            "result_filename": self.result_filename,
            "created_at": self.created_at,
        }
