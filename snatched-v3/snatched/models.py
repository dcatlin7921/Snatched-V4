from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class User(BaseModel):
    """User profile from PostgreSQL."""
    id: int
    username: str
    display_name: str | None = None
    created_at: datetime
    last_seen: datetime | None = None
    storage_quota_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GB default


class JobStatus(str, Enum):
    """Job lifecycle status values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    """Processing job as stored in PostgreSQL."""
    id: int
    user_id: int
    status: JobStatus
    upload_filename: str
    upload_size_bytes: int
    phases_requested: list[str]   # e.g., ['ingest', 'match', 'enrich', 'export']
    lanes_requested: list[str]    # e.g., ['memories', 'chats', 'stories']
    progress_pct: int = 0
    current_phase: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stats_json: dict | None = None


class JobCreate(BaseModel):
    """Request body to create a new processing job."""
    upload_filename: str
    upload_size_bytes: int = Field(gt=0)
    phases_requested: list[str]
    lanes_requested: list[str]


class JobEventType(str, Enum):
    """Job event types streamed via SSE."""
    PHASE_START = "phase_start"
    PROGRESS = "progress"
    MATCH_FOUND = "match_found"
    ERROR = "error"
    COMPLETE = "complete"


class JobEvent(BaseModel):
    """Single job event record for SSE streaming."""
    id: int
    job_id: int
    event_type: JobEventType
    message: str
    data_json: dict | None = None
    created_at: datetime


class MatchResult(BaseModel):
    """Single match result row."""
    asset_id: int
    strategy: str
    confidence: float
    is_best: bool
    matched_date: str | None = None
    matched_lat: float | None = None
    matched_lon: float | None = None
    display_name: str | None = None
    output_subdir: str | None = None
    output_filename: str | None = None


class AssetInfo(BaseModel):
    """Single asset metadata record."""
    id: int
    path: str
    filename: str
    date_str: str | None = None
    asset_type: str
    is_video: bool
    file_size: int
    sha256: str
    output_path: str | None = None
    exif_written: bool = False


class PipelineStats(BaseModel):
    """Summary statistics from a complete pipeline run."""
    total_assets: int = 0
    total_matched: int = 0
    total_exif_ok: int = 0
    total_exif_err: int = 0
    total_copied: int = 0
    gps_count: int = 0
    elapsed_seconds: float = 0.0


class UploadResponse(BaseModel):
    """Response after a successful file upload."""
    job_id: int
    upload_filename: str
    message: str
    redirect_url: str   # e.g., '/dashboard?job_id=123'
