import os
from pathlib import Path
import tomllib
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ServerConfig(BaseModel):
    """Server binding and runtime settings."""
    host: str = "0.0.0.0"
    port: int = 8000
    data_dir: Path = Path("/data")
    max_upload_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB
    dev_mode: bool = False  # Enable dev bypass for auth (NEVER True in production)
    promo_code: str = ""    # Promo code that unlocks Pro tier (empty = disabled)


class DatabaseConfig(BaseModel):
    """PostgreSQL connection settings."""
    postgres_url: str = "postgresql://snatched:snatched@postgres:5432/snatched"
    pool_min_size: int = 2
    pool_max_size: int = 10


class PipelineConfig(BaseModel):
    """Pipeline execution settings."""
    batch_size: int = 500           # Rows per SQLite commit batch
    gps_window_seconds: int = 300   # ±5 min for GPS cross-reference


class ExifConfig(BaseModel):
    """EXIF embedding settings."""
    enabled: bool = True
    tool: str = "exiftool"          # System binary name


class XmpConfig(BaseModel):
    """XMP sidecar generation settings."""
    enabled: bool = False
    alongside_exif: bool = True     # Generate XMP in addition to EXIF
    only: bool = False              # Generate XMP instead of EXIF
    include_snatched_ns: bool = True


class UploadConfig(BaseModel):
    """Chunked upload settings."""
    chunk_size_bytes: int = 5242880              # 5 MB per chunk
    max_file_bytes: int = 5368709120             # 5 GB per individual file
    max_total_bytes: int = 26843545600           # 25 GB total per session
    session_ttl_hours: int = 24                  # expire incomplete uploads after 24h
    max_concurrent_sessions: int = 1             # per user
    cleanup_interval_minutes: int = 60           # check for expired sessions


class LaneConfig(BaseModel):
    """Per-lane processing settings."""
    enabled: bool = True
    folder_pattern: str = "year_month"  # year_month, year, flat, type

    # Memories lane
    burn_overlays: bool = True

    # Chats lane
    export_text: bool = True
    export_png: bool = True
    dark_mode: bool = False
    chat_timestamps: bool = True
    chat_cover_pages: bool = True

    # Shared
    gps_precision: str = "exact"  # exact, city, none
    hide_sent_to: bool = False


class Config(BaseModel):
    """Complete application configuration."""
    server: ServerConfig = ServerConfig()
    database: DatabaseConfig = DatabaseConfig()
    pipeline: PipelineConfig = PipelineConfig()
    exif: ExifConfig = ExifConfig()
    xmp: XmpConfig = XmpConfig()
    upload: UploadConfig = UploadConfig()
    lanes: dict[str, LaneConfig] = {}


def load_config(toml_path: Path | None = None) -> Config:
    """Load configuration from TOML file with built-in defaults.

    Priority (lowest → highest):
    1. Built-in defaults (hardcoded in Config model)
    2. snatched.toml values (if file exists)

    Args:
        toml_path: Path to TOML config file. Defaults to /app/snatched.toml.

    Returns:
        Populated Config object.

    Raises:
        ValueError: If TOML file exists but has invalid syntax.
    """
    if toml_path is None:
        toml_path = Path("/app/snatched.toml")

    # Start with defaults
    config_data = {
        "server": ServerConfig().model_dump(),
        "database": DatabaseConfig().model_dump(),
        "pipeline": PipelineConfig().model_dump(),
        "exif": ExifConfig().model_dump(),
        "xmp": XmpConfig().model_dump(),
        "upload": UploadConfig().model_dump(),
        "lanes": {},
    }

    # Load from TOML if it exists
    if toml_path.exists():
        try:
            with open(toml_path, "rb") as f:
                toml_data = tomllib.load(f)

            # Merge TOML values into defaults
            if "server" in toml_data:
                config_data["server"].update(toml_data["server"])
            if "database" in toml_data:
                config_data["database"].update(toml_data["database"])
            if "pipeline" in toml_data:
                config_data["pipeline"].update(toml_data["pipeline"])
            if "exif" in toml_data:
                config_data["exif"].update(toml_data["exif"])
            if "xmp" in toml_data:
                config_data["xmp"].update(toml_data["xmp"])
            if "upload" in toml_data:
                config_data["upload"].update(toml_data["upload"])
            if "lanes" in toml_data:
                # Merge lane configs
                for lane_name, lane_config in toml_data["lanes"].items():
                    config_data["lanes"][lane_name] = {
                        **LaneConfig().model_dump(),
                        **lane_config,
                    }

            logger.info(f"Loaded configuration from {toml_path}")
        except Exception as e:
            raise ValueError(f"Invalid TOML syntax in {toml_path}: {e}") from e

    config = Config(**config_data)

    # Override postgres_url from Docker secret file if available
    pw_file = os.environ.get("DB_PASSWORD_FILE")
    if pw_file and Path(pw_file).is_file():
        password = Path(pw_file).read_text().strip()
        db_host = os.environ.get("DB_HOST", "memory-store")
        db_user = os.environ.get("DB_USER", "snatched")
        db_name = os.environ.get("DB_NAME", "snatched")
        config.database.postgres_url = (
            f"postgresql://{db_user}:{password}@{db_host}:5432/{db_name}"
        )
        logger.info("PostgreSQL URL built from Docker secret file")

    return config


def get_user_data_dir(config: Config, username: str) -> Path:
    """Return per-user data directory: config.server.data_dir / username.

    Args:
        config: Application configuration
        username: Authenticated username

    Returns:
        Path to user's data directory (not validated to exist)
    """
    return config.server.data_dir / username
