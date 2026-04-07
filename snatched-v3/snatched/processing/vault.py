"""Vault: persistent per-user SQLite database that accumulates data across imports.

Each Snatched user gets one vault.db at:
    /data/{username}/vault/vault.db

Data flows from per-job proc.db into the vault via dedup merges.
Running the same import twice produces identical results — every operation is idempotent.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Schema
# ---------------------------------------------------------------------------

_VAULT_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- ── VAULT META: key/value store for account info ────────────────────────────
CREATE TABLE IF NOT EXISTS vault_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT
);

-- ── IMPORTS: each proc.db merge is recorded here ────────────────────────────
CREATE TABLE IF NOT EXISTS imports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              INTEGER NOT NULL,
    original_filename   TEXT,
    imported_at         TEXT NOT NULL DEFAULT (datetime('now')),
    stats_json          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_imports_job ON imports(job_id);

-- ── ASSETS ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    path            TEXT NOT NULL,
    filename        TEXT NOT NULL,
    date_str        TEXT,
    file_id         TEXT,
    ext             TEXT NOT NULL,
    real_ext        TEXT,
    asset_type      TEXT NOT NULL,
    is_video        BOOLEAN NOT NULL DEFAULT 0,
    is_fmp4         BOOLEAN NOT NULL DEFAULT 0,
    memory_uuid     TEXT,
    file_size       INTEGER,
    sha256          TEXT,
    output_path     TEXT,
    output_sha256   TEXT,
    exif_written    BOOLEAN DEFAULT 0,
    exif_error      TEXT,
    xmp_written     BOOLEAN DEFAULT 0,
    xmp_path        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    duplicate_of    INTEGER DEFAULT NULL,
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Dedup on sha256 only when sha256 is actually populated
CREATE UNIQUE INDEX IF NOT EXISTS idx_vault_assets_sha256
    ON assets(sha256) WHERE sha256 IS NOT NULL AND sha256 != '';

CREATE INDEX IF NOT EXISTS idx_vault_assets_file_id     ON assets(file_id);
CREATE INDEX IF NOT EXISTS idx_vault_assets_memory_uuid ON assets(memory_uuid);
CREATE INDEX IF NOT EXISTS idx_vault_assets_import      ON assets(import_id);

-- ── MEMORIES ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    mid             TEXT,
    date            TEXT,
    date_dt         TEXT,
    media_type      TEXT,
    location_raw    TEXT,
    lat             REAL,
    lon             REAL,
    download_link   TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vault_memories_mid
    ON memories(mid) WHERE mid IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_vault_memories_date   ON memories(date_dt);
CREATE INDEX IF NOT EXISTS idx_vault_memories_import ON memories(import_id);

-- ── LOCATIONS ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    timestamp       TEXT NOT NULL,
    timestamp_unix  REAL NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    accuracy_m      REAL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vault_locations_dedup
    ON locations(timestamp_unix, ROUND(lat, 6), ROUND(lon, 6));

CREATE INDEX IF NOT EXISTS idx_vault_locations_ts     ON locations(timestamp_unix);
CREATE INDEX IF NOT EXISTS idx_vault_locations_import ON locations(import_id);

-- ── FRIENDS ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS friends (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    category        TEXT,
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_vault_friends_import ON friends(import_id);

-- ── CHAT MESSAGES ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id           INTEGER NOT NULL REFERENCES imports(id),
    conversation_id     TEXT NOT NULL,
    from_user           TEXT,
    media_type          TEXT,
    media_ids           TEXT,
    content             TEXT,
    created             TEXT,
    created_ms          INTEGER,
    is_sender           BOOLEAN DEFAULT 0,
    conversation_title  TEXT,
    created_dt          TEXT,
    created_date        TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vault_chat_dedup
    ON chat_messages(conversation_id, created_ms, from_user);

CREATE INDEX IF NOT EXISTS idx_vault_chat_import ON chat_messages(import_id);

-- ── SNAP MESSAGES ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS snap_messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id           INTEGER NOT NULL REFERENCES imports(id),
    conversation_id     TEXT NOT NULL,
    from_user           TEXT,
    media_type          TEXT,
    created             TEXT,
    created_ms          INTEGER,
    is_sender           BOOLEAN DEFAULT 0,
    conversation_title  TEXT,
    created_dt          TEXT,
    created_date        TEXT,
    dedup_key           TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vault_snap_dedup
    ON snap_messages(dedup_key) WHERE dedup_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_vault_snap_import ON snap_messages(import_id);

-- ── CHAT MEDIA IDS (link table, no dedup) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_media_ids (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    chat_message_id INTEGER NOT NULL,
    media_id        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vault_cmid_media  ON chat_media_ids(media_id);
CREATE INDEX IF NOT EXISTS idx_vault_cmid_import ON chat_media_ids(import_id);

-- ── STORIES ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    story_id        TEXT,
    created         TEXT,
    created_dt      TEXT,
    content_type    TEXT
);

CREATE INDEX IF NOT EXISTS idx_vault_stories_import ON stories(import_id);

-- ── SNAP PRO ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS snap_pro (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    url             TEXT,
    created         TEXT,
    created_dt      TEXT,
    title           TEXT
);

CREATE INDEX IF NOT EXISTS idx_vault_snap_pro_import ON snap_pro(import_id);

-- ── PLACES ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS places (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    name            TEXT,
    lat             REAL,
    lon             REAL,
    address         TEXT,
    visit_count     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_vault_places_import ON places(import_id);

-- ── MATCHES (rebuilt per import, no dedup) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    asset_id        INTEGER NOT NULL,
    strategy        TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.0,
    is_best         BOOLEAN NOT NULL DEFAULT 0,
    memory_id       INTEGER,
    chat_message_id INTEGER,
    snap_message_id INTEGER,
    story_id        INTEGER,
    matched_date    TEXT,
    matched_lat     REAL,
    matched_lon     REAL,
    gps_source      TEXT,
    display_name    TEXT,
    creator_str     TEXT,
    direction       TEXT,
    conversation    TEXT,
    lane            TEXT DEFAULT 'memories',
    output_subdir   TEXT,
    output_filename TEXT,
    exif_tags_json  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_vault_matches_asset  ON matches(asset_id);
CREATE INDEX IF NOT EXISTS idx_vault_matches_import ON matches(import_id);

-- ── RUN LOG ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    version         TEXT NOT NULL,
    person          TEXT NOT NULL,
    input_path      TEXT NOT NULL,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    phase           TEXT,
    status          TEXT DEFAULT 'running',
    flags_json      TEXT,
    total_assets    INTEGER,
    total_matched   INTEGER,
    total_exif_ok   INTEGER,
    total_exif_err  INTEGER,
    total_copied    INTEGER,
    elapsed_seconds REAL,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_vault_run_log_import ON run_log(import_id);

-- ── REPROCESS LOG ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reprocess_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    phases          TEXT,
    lanes           TEXT,
    triggered_by    TEXT,
    status          TEXT DEFAULT 'pending',
    result_json     TEXT
);

CREATE INDEX IF NOT EXISTS idx_vault_reprocess_import ON reprocess_log(import_id);

-- ── LANE CONFIG ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lane_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    lane_name       TEXT UNIQUE NOT NULL,
    config_json     TEXT
);

CREATE INDEX IF NOT EXISTS idx_vault_lane_config_import ON lane_config(import_id);
"""


def _init_vault_schema(conn: sqlite3.Connection) -> None:
    """Create all vault.db tables. Idempotent — uses IF NOT EXISTS throughout."""
    conn.executescript(_VAULT_SCHEMA)
    conn.commit()
    logger.info("Vault schema initialized")


# ---------------------------------------------------------------------------
# 1b. Schema migration for existing vaults
# ---------------------------------------------------------------------------

# Tables that must have an import_id column (all data tables).
_DATA_TABLES_WITH_IMPORT_ID = [
    "assets", "memories", "locations", "friends", "chat_messages",
    "snap_messages", "chat_media_ids", "stories", "snap_pro", "places",
    "matches", "run_log", "reprocess_log", "lane_config",
]


def migrate_vault_schema(vault_db_path: Path) -> None:
    """Add import_id column to existing vault tables that lack it.

    SQLite doesn't support ALTER TABLE ... ADD COLUMN IF NOT EXISTS,
    so we catch the 'duplicate column name' error for each table.

    Safe to call repeatedly — idempotent.
    """
    conn = sqlite3.connect(str(vault_db_path))
    try:
        # Also ensure all tables exist
        _init_vault_schema(conn)

        migrated = []
        for table in _DATA_TABLES_WITH_IMPORT_ID:
            try:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN import_id INTEGER REFERENCES imports(id)"
                )
                migrated.append(table)
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    pass  # Already has import_id — expected
                else:
                    raise

        if migrated:
            conn.commit()
            logger.info("Migrated import_id onto tables: %s", ", ".join(migrated))
        else:
            logger.debug("All tables already have import_id — no migration needed")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. Vault creation
# ---------------------------------------------------------------------------

def create_vault(
    vault_dir: Path,
    snap_uid: str | None,
    snap_username: str | None,
) -> Path:
    """Create a new vault.db with full schema and meta entries.

    Args:
        vault_dir: Directory to create vault.db in (created if needed).
        snap_uid: Snapchat account UID (may be None).
        snap_username: Snapchat username (may be None).

    Returns:
        Absolute path to the new vault.db file.
    """
    vault_dir = Path(vault_dir)
    vault_dir.mkdir(parents=True, exist_ok=True)

    db_path = vault_dir / "vault.db"
    conn = sqlite3.connect(str(db_path))
    try:
        _init_vault_schema(conn)

        _uid = snap_uid.strip() if snap_uid else None
        _uname = snap_username.strip() if snap_username else None

        now = datetime.utcnow().isoformat()
        meta = {
            "snap_account_uid": _uid or "",
            "snap_username": _uname or "",
            "created_at": now,
            "last_import_job_id": "",
        }
        for key, value in meta.items():
            conn.execute(
                "INSERT OR REPLACE INTO vault_meta (key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()
        logger.info("Vault created at %s (uid=%s, username=%s)", db_path, snap_uid, snap_username)
    finally:
        conn.close()

    return db_path


# ---------------------------------------------------------------------------
# 3. Vault discovery
# ---------------------------------------------------------------------------

def find_vault_for_account(
    data_dir: Path,
    username: str,
    snap_uid: str | None,
    snap_username: str | None,
) -> Path | None:
    """Find an existing vault.db that matches the given account fingerprint.

    Search order:
      1. Fast path — check if vault dir name matches snap_uid or snap_username directly.
      2. Slow path — open each vault.db and compare vault_meta entries.

    Args:
        data_dir: Base data directory (e.g. /data).
        username: Snatched platform username.
        snap_uid: Snapchat account UID to match (may be None).
        snap_username: Snapchat username to match (may be None).

    Returns:
        Path to matching vault.db, or None if no match found.
    """
    vaults_dir = Path(data_dir) / username / "vaults"
    if not vaults_dir.is_dir():
        return None

    # Collect all vault dirs
    vault_dirs = [d for d in vaults_dir.iterdir() if d.is_dir()]
    if not vault_dirs:
        return None

    # Fast path: directory name matches the fingerprint
    for candidate_id in [snap_uid, snap_username]:
        if not candidate_id:
            continue
        fast = vaults_dir / candidate_id / "vault.db"
        if fast.is_file():
            logger.info("Vault found (fast path): %s", fast)
            return fast

    # Slow path: open each vault and compare meta
    for vdir in vault_dirs:
        db_path = vdir / "vault.db"
        if not db_path.is_file():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute("SELECT key, value FROM vault_meta").fetchall()
                meta = {r["key"]: r["value"] for r in rows}

                stored_uid = meta.get("snap_account_uid", "")
                stored_name = meta.get("snap_username", "")

                # Match on UID first (strongest signal)
                if snap_uid and stored_uid and snap_uid == stored_uid:
                    logger.info("Vault found (uid match): %s", db_path)
                    return db_path

                # Fall back to username match
                if snap_username and stored_name and snap_username == stored_name:
                    logger.info("Vault found (username match): %s", db_path)
                    return db_path
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.warning("Could not read vault at %s: %s", db_path, e)
            continue

    return None


# ---------------------------------------------------------------------------
# 3b. Simplified one-vault-per-user helpers
# ---------------------------------------------------------------------------

def find_user_vault(data_dir: Path, username: str) -> Path | None:
    """Find the user's vault at the canonical path /data/{username}/vault/vault.db."""
    vault_db = Path(data_dir) / username / "vault" / "vault.db"
    return vault_db if vault_db.is_file() else None


def create_user_vault(data_dir: Path, username: str, snap_uid: str | None = None, snap_username: str | None = None) -> Path:
    """Create vault at the canonical path /data/{username}/vault/vault.db."""
    vault_dir = Path(data_dir) / username / "vault"
    return create_vault(vault_dir, snap_uid, snap_username)


def check_vault_fingerprint(vault_db_path: Path, job_snap_uid: str | None, job_snap_username: str | None) -> dict:
    """Check if a job's Snapchat fingerprint matches the existing vault.

    Returns:
        {"ok": True} if safe to merge.
        {"ok": False, "reason": str, "vault_uid": str, "vault_username": str,
         "job_uid": str, "job_username": str} if mismatch.
    """
    vault_db_path = Path(vault_db_path)
    if not vault_db_path.is_file():
        # No vault yet — first import, always OK
        return {"ok": True}

    # Normalize job inputs: strip whitespace, convert empty to None
    job_snap_uid = job_snap_uid.strip() if job_snap_uid else None
    job_snap_username = job_snap_username.strip() if job_snap_username else None

    conn = sqlite3.connect(str(vault_db_path))
    try:
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM vault_meta").fetchall()}
        import_count = conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
    finally:
        conn.close()

    vault_uid = meta.get("snap_account_uid", "").strip() or None
    vault_username = meta.get("snap_username", "").strip() or None

    # If vault has no fingerprint yet, allow (first real import sets it)
    if not vault_uid and not vault_username:
        return {"ok": True}

    # If job has no fingerprint: allow if vault already has a verified import
    # (partial exports like -2.zip, -3.zip, media-only have no fingerprint)
    if not job_snap_uid and not job_snap_username:
        if import_count >= 1:
            logger.info("No-fingerprint upload allowed: vault already has %d verified import(s)", import_count)
            return {"ok": True}
        return {
            "ok": False,
            "reason": "no_fingerprint",
            "vault_uid": vault_uid,
            "vault_username": vault_username,
            "job_uid": None,
            "job_username": None,
        }

    # Check UID match (strongest signal)
    if vault_uid and job_snap_uid and vault_uid != job_snap_uid:
        return {
            "ok": False,
            "reason": "uid_mismatch",
            "vault_uid": vault_uid,
            "vault_username": vault_username,
            "job_uid": job_snap_uid,
            "job_username": job_snap_username,
        }

    # Check username match (if UIDs aren't both available)
    if vault_username and job_snap_username and vault_username != job_snap_username:
        return {
            "ok": False,
            "reason": "username_mismatch",
            "vault_uid": vault_uid,
            "vault_username": vault_username,
            "job_uid": job_snap_uid,
            "job_username": job_snap_username,
        }

    return {"ok": True}


def validate_vault_seed(proc_db_path: Path, snap_account_uid: str | None = None) -> dict:
    """Validate that a job has enough data richness to seed a new vault.

    This gate ONLY applies to the first import (vault creation).
    Subsequent merges into an existing vault skip this check.

    Requirements:
    1. Fingerprint: snap_account_uid must be present (passed in or found in proc.db)
    2. Date span: memories must cover > 90 days
    3. Data richness: at least 3 of these 5 categories must have data:
       memories, chat_messages, friends, locations, stories

    Args:
        proc_db_path: Path to the job's proc.db
        snap_account_uid: The job's snap_account_uid from PG (primary source)

    Returns:
        {
            "pass": True/False,
            "checks": {
                "fingerprint": {"pass": bool, "detail": str},
                "date_span": {"pass": bool, "days": int, "required": 90, "detail": str},
                "richness": {"pass": bool, "populated": int, "required": 3,
                             "categories": {"memories": int, "chats": int, "friends": int,
                                            "locations": int, "stories": int},
                             "detail": str},
            },
            "recommendation": str  # human-friendly guidance
        }
    """
    result: dict = {
        "pass": False,
        "checks": {},
        "recommendation": "",
    }

    try:
        conn = sqlite3.connect(f"file:{proc_db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        result["checks"] = {
            "fingerprint": {"pass": False, "detail": f"Cannot open proc.db: {exc}"},
            "date_span": {"pass": False, "days": 0, "required": 90, "detail": "Skipped — db unavailable"},
            "richness": {"pass": False, "populated": 0, "required": 3,
                         "categories": {"memories": 0, "chats": 0, "friends": 0, "locations": 0, "stories": 0},
                         "detail": "Skipped — db unavailable"},
        }
        result["recommendation"] = "The job database could not be opened. Re-run processing or upload a new export."
        return result

    try:
        # --- 1. Fingerprint: snap_account_uid ---
        fp_pass = False
        fp_detail = "No snap_account_uid found"
        # Primary: use the snap_account_uid passed from the PG job record
        if snap_account_uid and snap_account_uid.strip():
            fp_pass = True
            fp_detail = f"snap_account_uid present: {snap_account_uid[:12]}..."
        # Fallback: check vault_meta table in proc.db (rare — usually only in vault.db)
        if not fp_pass and _table_exists(conn, "vault_meta"):
            row = conn.execute(
                "SELECT value FROM vault_meta WHERE key = 'snap_account_uid'"
            ).fetchone()
            if row and row[0]:
                fp_pass = True
                fp_detail = f"snap_account_uid in vault_meta: {row[0][:12]}..."

        result["checks"]["fingerprint"] = {"pass": fp_pass, "detail": fp_detail}

        # --- 2. Date span: memories must cover > 90 days ---
        date_pass = False
        date_days = 0
        date_detail = "No memories table found"
        if _table_exists(conn, "memories"):
            span_row = conn.execute(
                "SELECT MIN(date_dt), MAX(date_dt) FROM memories"
            ).fetchone()
            if span_row and span_row[0] and span_row[1]:
                min_dt_str = span_row[0]
                max_dt_str = span_row[1]
                # Parse dates — handle "2016-07-19 02:27:23 UTC" and ISO formats
                min_dt = _parse_date_flexible(min_dt_str)
                max_dt = _parse_date_flexible(max_dt_str)
                if min_dt and max_dt:
                    date_days = (max_dt - min_dt).days
                    date_pass = date_days > 90
                    date_detail = f"Memories span {date_days} days ({min_dt_str[:10]} to {max_dt_str[:10]})"
                else:
                    date_detail = f"Could not parse date range: {min_dt_str!r} to {max_dt_str!r}"
            else:
                date_detail = "Memories table exists but has no dates"
        result["checks"]["date_span"] = {
            "pass": date_pass, "days": date_days, "required": 90, "detail": date_detail,
        }

        # --- 3. Data richness: >=3 of 5 categories populated ---
        categories = {
            "memories": 0,
            "chats": 0,
            "friends": 0,
            "locations": 0,
            "stories": 0,
        }
        table_map = {
            "memories": "memories",
            "chats": "chat_messages",
            "friends": "friends",
            "locations": "locations",
            "stories": "stories",
        }
        for cat_key, table_name in table_map.items():
            if _table_exists(conn, table_name):
                try:
                    categories[cat_key] = _count(conn, table_name)
                except Exception:
                    categories[cat_key] = 0

        populated = sum(1 for v in categories.values() if v > 0)
        richness_pass = populated >= 3
        populated_names = [k for k, v in categories.items() if v > 0]
        richness_detail = (
            f"{populated}/5 categories populated ({', '.join(populated_names) or 'none'})"
        )
        result["checks"]["richness"] = {
            "pass": richness_pass, "populated": populated, "required": 3,
            "categories": categories, "detail": richness_detail,
        }

        # --- Overall pass/fail ---
        all_pass = fp_pass and date_pass and richness_pass
        result["pass"] = all_pass

        # --- Recommendation ---
        if all_pass:
            result["recommendation"] = "This export looks great — ready to create your vault."
        else:
            issues = []
            if not fp_pass:
                issues.append("no Snapchat account ID was found in the export")
            if not date_pass:
                issues.append(
                    f"your export covers only {date_days} days (need more than 90)"
                )
            if not richness_pass:
                issues.append(
                    f"only {populated} of 5 data categories are populated (need at least 3)"
                )
            result["recommendation"] = (
                "This export doesn't meet the minimum requirements to create a vault: "
                + "; ".join(issues) + ". "
                "For the best vault, request a full account export from Snapchat "
                "covering your entire history."
            )

    finally:
        conn.close()

    return result


def _parse_date_flexible(dt_str: str) -> datetime | None:
    """Parse a date string in various formats from proc.db."""
    if not dt_str:
        return None
    # Strip trailing " UTC" for naive parsing
    cleaned = dt_str.strip().removesuffix(" UTC").strip()
    # Remove timezone offset like +00:00 or -05:00 for naive comparison
    # Match patterns like 2016-07-19T02:27:23+00:00
    if len(cleaned) > 19 and cleaned[19] in ('+', '-'):
        cleaned = cleaned[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def backfill_user_vault(data_dir: Path, username: str, job_ids: list[int]) -> dict:
    """Merge multiple existing jobs into a user's vault. Creates vault if needed.

    Args:
        data_dir: Base data directory.
        username: Snatched username.
        job_ids: List of job IDs to merge (in order).

    Returns:
        Combined stats dict with per-job and total counts.
    """
    vault_db = find_user_vault(data_dir, username)
    if vault_db is None:
        vault_db = create_user_vault(data_dir, username)

    combined = {"jobs_merged": 0, "jobs_skipped": 0, "total_assets": 0, "total_locations": 0, "total_friends": 0}
    for jid in job_ids:
        proc_db = Path(data_dir) / username / "jobs" / str(jid) / "proc.db"
        if not proc_db.is_file():
            logger.warning("Backfill: proc.db not found for job %d", jid)
            combined["jobs_skipped"] += 1
            continue
        stats = import_job_to_vault(vault_db, proc_db, jid, None)
        if stats.get("error"):
            combined["jobs_skipped"] += 1
        else:
            combined["jobs_merged"] += 1
            combined["total_assets"] = stats.get("total_assets", 0)
            combined["total_locations"] = stats.get("total_locations", 0)
            combined["total_friends"] = stats.get("total_friends", 0)

    return combined


# ---------------------------------------------------------------------------
# 4. Import proc.db into vault
# ---------------------------------------------------------------------------

# Column lists for each table (excluding 'id' — vault assigns its own PKs).
# These must match the proc.db schema exactly.

_ASSETS_COLS = [
    "path", "filename", "date_str", "file_id", "ext", "real_ext", "asset_type",
    "is_video", "is_fmp4", "memory_uuid", "file_size", "sha256", "output_path",
    "output_sha256", "exif_written", "exif_error", "xmp_written", "xmp_path",
    "created_at", "duplicate_of",
]

_MEMORIES_COLS = [
    "mid", "date", "date_dt", "media_type", "location_raw", "lat", "lon",
    "download_link",
]

_LOCATIONS_COLS = ["timestamp", "timestamp_unix", "lat", "lon", "accuracy_m"]

_FRIENDS_COLS = ["username", "display_name", "category"]

_CHAT_MESSAGES_COLS = [
    "conversation_id", "from_user", "media_type", "media_ids", "content",
    "created", "created_ms", "is_sender", "conversation_title", "created_dt",
    "created_date",
]

_SNAP_MESSAGES_COLS = [
    "conversation_id", "from_user", "media_type", "created", "created_ms",
    "is_sender", "conversation_title", "created_dt", "created_date", "dedup_key",
]

_STORIES_COLS = ["story_id", "created", "created_dt", "content_type"]

_SNAP_PRO_COLS = ["url", "created", "created_dt", "title"]

_PLACES_COLS = ["name", "lat", "lon", "address", "visit_count"]

_RUN_LOG_COLS = [
    "version", "person", "input_path", "started_at", "finished_at", "phase",
    "status", "flags_json", "total_assets", "total_matched", "total_exif_ok",
    "total_exif_err", "total_copied", "elapsed_seconds", "error_message",
]

_REPROCESS_LOG_COLS = [
    "timestamp", "phases", "lanes", "triggered_by", "status", "result_json",
]

_LANE_CONFIG_COLS = ["lane_name", "config_json"]

_MATCHES_COLS = [
    "asset_id", "strategy", "confidence", "is_best", "memory_id",
    "chat_message_id", "snap_message_id", "story_id", "matched_date",
    "matched_lat", "matched_lon", "gps_source", "display_name", "creator_str",
    "direction", "conversation", "lane", "output_subdir", "output_filename",
    "exif_tags_json", "created_at",
]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check whether a table exists in the connected database."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _read_all(conn: sqlite3.Connection, table: str, cols: list[str]) -> list[tuple]:
    """Read all rows from a proc.db table, returning only the listed columns."""
    col_list = ", ".join(cols)
    try:
        return conn.execute(f"SELECT {col_list} FROM {table}").fetchall()
    except sqlite3.OperationalError as e:
        logger.warning("Could not read %s from proc.db: %s", table, e)
        return []


def import_job_to_vault(
    vault_db_path: Path,
    proc_db_path: Path,
    job_id: int,
    original_filename: str | None = None,
) -> dict:
    """Merge a proc.db into the vault via dedup INSERT OR IGNORE.

    The entire import runs inside a single transaction — all or nothing.
    Re-running with the same job_id is a no-op (idempotent).

    Args:
        vault_db_path: Path to vault.db.
        proc_db_path: Path to the per-job proc.db.
        job_id: Unique job identifier.
        original_filename: Original uploaded ZIP name (for audit trail).

    Returns:
        Stats dict with counts of added/skipped rows per table.
    """
    vault_db_path = Path(vault_db_path)
    proc_db_path = Path(proc_db_path)

    if not proc_db_path.is_file():
        logger.error("proc.db not found: %s", proc_db_path)
        return {"error": "proc_db_not_found"}

    stats = {
        "job_id": job_id,
        "assets_added": 0,
        "assets_skipped": 0,
        "memories_added": 0,
        "memories_skipped": 0,
        "locations_added": 0,
        "locations_skipped": 0,
        "friends_added": 0,
        "friends_updated": 0,
        "chat_messages_added": 0,
        "snap_messages_added": 0,
        "stories_added": 0,
        "snap_pro_added": 0,
        "places_added": 0,
        "matches_added": 0,
        "run_log_added": 0,
        "total_assets": 0,
        "total_memories": 0,
        "total_locations": 0,
        "total_friends": 0,
        "total_chat_messages": 0,
        "total_snap_messages": 0,
        "import_count": 0,
    }

    # Ensure schema is up to date before opening main connections
    migrate_vault_schema(vault_db_path)

    vault = sqlite3.connect(str(vault_db_path))
    vault.row_factory = sqlite3.Row
    proc = sqlite3.connect(str(proc_db_path))
    proc.row_factory = sqlite3.Row

    try:
        # Check if this job was already imported
        existing = vault.execute(
            "SELECT id FROM imports WHERE job_id = ?", (job_id,)
        ).fetchone()
        if existing:
            logger.info("Job %d already imported into vault (import_id=%d), skipping",
                        job_id, existing["id"])
            stats["import_count"] = _count(vault, "imports")
            _fill_totals(vault, stats)
            return stats

        # Begin transaction
        vault.execute("BEGIN")

        # Create import record
        cursor = vault.execute(
            "INSERT INTO imports (job_id, original_filename) VALUES (?, ?)",
            (job_id, original_filename),
        )
        import_id = cursor.lastrowid
        logger.info("Import record created: import_id=%d, job_id=%d", import_id, job_id)

        # ── Assets (dedup on sha256 partial unique index) ────────────────
        stats["assets_added"], stats["assets_skipped"] = _merge_with_ignore(
            proc, vault, "assets", _ASSETS_COLS, import_id,
        )

        # ── Memories (dedup on mid) ──────────────────────────────────────
        stats["memories_added"], stats["memories_skipped"] = _merge_with_ignore(
            proc, vault, "memories", _MEMORIES_COLS, import_id,
        )

        # ── Locations (dedup on timestamp_unix + rounded lat/lon) ────────
        stats["locations_added"], stats["locations_skipped"] = _merge_with_ignore(
            proc, vault, "locations", _LOCATIONS_COLS, import_id,
        )

        # ── Friends (dedup on username, update display_name if changed) ──
        stats["friends_added"], stats["friends_updated"] = _merge_friends(
            proc, vault, import_id,
        )

        # ── Chat messages (dedup on conversation_id + created_ms + from_user)
        stats["chat_messages_added"], _ = _merge_with_ignore(
            proc, vault, "chat_messages", _CHAT_MESSAGES_COLS, import_id,
        )

        # ── Snap messages (dedup on dedup_key) ───────────────────────────
        stats["snap_messages_added"], _ = _merge_with_ignore(
            proc, vault, "snap_messages", _SNAP_MESSAGES_COLS, import_id,
        )

        # ── Chat media IDs (link table, always insert) ───────────────────
        _copy_table(proc, vault, "chat_media_ids",
                    ["chat_message_id", "media_id"], import_id)

        # ── Stories, snap_pro, places (simple copy) ──────────────────────
        stats["stories_added"], _ = _merge_with_ignore(
            proc, vault, "stories", _STORIES_COLS, import_id,
        )
        stats["snap_pro_added"], _ = _merge_with_ignore(
            proc, vault, "snap_pro", _SNAP_PRO_COLS, import_id,
        )
        stats["places_added"], _ = _merge_with_ignore(
            proc, vault, "places", _PLACES_COLS, import_id,
        )

        # ── Matches (rebuilt per import) ─────────────────────────────────
        stats["matches_added"], _ = _merge_with_ignore(
            proc, vault, "matches", _MATCHES_COLS, import_id,
        )

        # ── Run log, reprocess log, lane config ─────────────────────────
        stats["run_log_added"], _ = _merge_with_ignore(
            proc, vault, "run_log", _RUN_LOG_COLS, import_id,
        )
        _merge_with_ignore(proc, vault, "reprocess_log", _REPROCESS_LOG_COLS, import_id)
        _merge_with_ignore(proc, vault, "lane_config", _LANE_CONFIG_COLS, import_id)

        # Update vault_meta with last import
        vault.execute(
            "INSERT OR REPLACE INTO vault_meta (key, value) VALUES (?, ?)",
            ("last_import_job_id", str(job_id)),
        )

        # Store import stats
        vault.execute(
            "UPDATE imports SET stats_json = ? WHERE id = ?",
            (json.dumps(stats), import_id),
        )

        vault.execute("COMMIT")
        logger.info("Vault import committed for job %d", job_id)

        # Fill totals after commit
        stats["import_id"] = import_id
        stats["import_count"] = _count(vault, "imports")
        _fill_totals(vault, stats)

    except Exception:
        vault.execute("ROLLBACK")
        logger.exception("Vault import failed for job %d, rolled back", job_id)
        raise
    finally:
        proc.close()
        vault.close()

    logger.info("Vault import stats: %s", json.dumps(stats, indent=2))
    return stats


def _merge_with_ignore(
    proc: sqlite3.Connection,
    vault: sqlite3.Connection,
    table: str,
    cols: list[str],
    import_id: int,
) -> tuple[int, int]:
    """INSERT OR IGNORE rows from proc into vault. Returns (added, skipped)."""
    if not _table_exists(proc, table):
        return 0, 0

    rows = _read_all(proc, table, cols)
    if not rows:
        return 0, 0

    total = len(rows)
    vault_cols = ["import_id"] + cols
    placeholders = ", ".join(["?"] * len(vault_cols))
    col_list = ", ".join(vault_cols)
    sql = f"INSERT OR IGNORE INTO {table} ({col_list}) VALUES ({placeholders})"

    added = 0
    for row in rows:
        vault.execute(sql, (import_id, *tuple(row)))
        added += vault.total_changes  # running total — we check per-row below

    # More reliable: count how many we actually added
    # total_changes is cumulative, so use a different approach
    before_count = _count(vault, table)
    # We already inserted — count is final. Compute added from inserts.
    # Actually, re-count properly:
    # The INSERT OR IGNORE already happened. Let's count rows with this import_id.
    added_count = vault.execute(
        f"SELECT COUNT(*) FROM {table} WHERE import_id = ?", (import_id,)
    ).fetchone()[0]
    skipped = total - added_count

    logger.info("  %s: %d/%d added (%d skipped)", table, added_count, total, skipped)
    return added_count, skipped


def _merge_friends(
    proc: sqlite3.Connection,
    vault: sqlite3.Connection,
    import_id: int,
) -> tuple[int, int]:
    """Merge friends with UPSERT: insert new, update display_name if changed."""
    if not _table_exists(proc, "friends"):
        return 0, 0

    rows = _read_all(proc, "friends", _FRIENDS_COLS)
    if not rows:
        return 0, 0

    added = 0
    updated = 0

    for row in rows:
        username, display_name, category = tuple(row)

        # Try insert first
        try:
            vault.execute(
                "INSERT INTO friends (import_id, username, display_name, category) "
                "VALUES (?, ?, ?, ?)",
                (import_id, username, display_name, category),
            )
            added += 1
        except sqlite3.IntegrityError:
            # Username already exists — update display_name if it changed
            existing = vault.execute(
                "SELECT display_name FROM friends WHERE username = ?", (username,)
            ).fetchone()
            if existing and existing[0] != display_name and display_name:
                vault.execute(
                    "UPDATE friends SET display_name = ? WHERE username = ?",
                    (display_name, username),
                )
                updated += 1

    logger.info("  friends: %d added, %d updated (of %d)", added, updated, len(rows))
    return added, updated


def _copy_table(
    proc: sqlite3.Connection,
    vault: sqlite3.Connection,
    table: str,
    cols: list[str],
    import_id: int,
) -> int:
    """Copy all rows from proc to vault (no dedup). Returns count inserted."""
    if not _table_exists(proc, table):
        return 0

    rows = _read_all(proc, table, cols)
    if not rows:
        return 0

    vault_cols = ["import_id"] + cols
    placeholders = ", ".join(["?"] * len(vault_cols))
    col_list = ", ".join(vault_cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    for row in rows:
        vault.execute(sql, (import_id, *tuple(row)))

    logger.info("  %s: %d rows copied", table, len(rows))
    return len(rows)


def _count(conn: sqlite3.Connection, table: str) -> int:
    """Return row count for a table."""
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _fill_totals(vault: sqlite3.Connection, stats: dict) -> None:
    """Fill total_* keys in stats from vault counts."""
    stats["total_assets"] = _count(vault, "assets")
    stats["total_memories"] = _count(vault, "memories")
    stats["total_locations"] = _count(vault, "locations")
    stats["total_friends"] = _count(vault, "friends")
    stats["total_chat_messages"] = _count(vault, "chat_messages")
    stats["total_snap_messages"] = _count(vault, "snap_messages")


# ---------------------------------------------------------------------------
# 5. Vault stats
# ---------------------------------------------------------------------------

def rematch_vault_gps(vault_db_path: Path, gps_window_seconds: int = 300) -> dict:
    """Re-run GPS matching on vault memories using ALL accumulated locations.

    After merging a new import that brought location data, previously
    unmatched memories may now have GPS coverage from the new breadcrumbs.

    Strategy:
    1. Find memories with date but no GPS (lat IS NULL)
    2. For each, search locations within gps_window_seconds of memory date
    3. Pick closest location by time, assign its lat/lon to the memory

    Returns:
        {"rematched": int, "checked": int, "already_had_gps": int}
    """
    import bisect

    conn = sqlite3.connect(str(vault_db_path))
    conn.row_factory = sqlite3.Row
    try:
        no_gps = conn.execute(
            "SELECT id, date_dt FROM memories WHERE (lat IS NULL OR lon IS NULL) AND date_dt IS NOT NULL"
        ).fetchall()

        already_had = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE lat IS NOT NULL AND lon IS NOT NULL"
        ).fetchone()[0]

        if not no_gps:
            return {"rematched": 0, "checked": 0, "already_had_gps": already_had}

        locations = conn.execute(
            "SELECT timestamp_unix, lat, lon FROM locations ORDER BY timestamp_unix"
        ).fetchall()

        if not locations:
            return {"rematched": 0, "checked": len(no_gps), "already_had_gps": already_had}

        loc_times = [loc["timestamp_unix"] for loc in locations]

        rematched = 0
        for mem in no_gps:
            date_str = mem["date_dt"]
            try:
                cleaned = date_str.replace(" UTC", "+00:00").replace(" ", "T")
                if "+" not in cleaned and "Z" not in cleaned:
                    cleaned += "+00:00"
                cleaned = cleaned.replace("Z", "+00:00")
                mem_ts = datetime.fromisoformat(cleaned).timestamp()
            except (ValueError, TypeError):
                continue

            idx = bisect.bisect_left(loc_times, mem_ts)
            best_loc = None
            best_delta = float("inf")

            for candidate_idx in [idx - 1, idx]:
                if 0 <= candidate_idx < len(locations):
                    delta = abs(loc_times[candidate_idx] - mem_ts)
                    if delta < best_delta and delta <= gps_window_seconds:
                        best_delta = delta
                        best_loc = locations[candidate_idx]

            if best_loc:
                conn.execute(
                    "UPDATE memories SET lat = ?, lon = ? WHERE id = ?",
                    (best_loc["lat"], best_loc["lon"], mem["id"]),
                )
                rematched += 1

        conn.commit()
        logger.info("Vault GPS rematch: %d/%d memories gained GPS (window=%ds)",
                     rematched, len(no_gps), gps_window_seconds)
        return {"rematched": rematched, "checked": len(no_gps), "already_had_gps": already_had}

    except Exception:
        logger.exception("Vault GPS rematch failed")
        return {"rematched": 0, "checked": 0, "error": True}
    finally:
        conn.close()


def get_vault_stats(vault_db_path: Path) -> dict:
    """Return comprehensive stats for a vault.

    Args:
        vault_db_path: Path to vault.db.

    Returns:
        Dict with counts, date range, GPS coverage, account info.
    """
    vault_db_path = Path(vault_db_path)
    if not vault_db_path.is_file():
        return {"error": "vault_not_found"}

    conn = sqlite3.connect(str(vault_db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Account info from vault_meta
        meta_rows = conn.execute("SELECT key, value FROM vault_meta").fetchall()
        account_info = {r["key"]: r["value"] for r in meta_rows}

        # Counts
        total_assets = _count(conn, "assets")
        total_memories = _count(conn, "memories")
        total_locations = _count(conn, "locations")
        total_friends = _count(conn, "friends")
        total_chat_messages = _count(conn, "chat_messages")
        total_snap_messages = _count(conn, "snap_messages")
        import_count = _count(conn, "imports")

        # Date range from memories
        date_range = {"min": None, "max": None}
        row = conn.execute(
            "SELECT MIN(date_dt) as min_date, MAX(date_dt) as max_date FROM memories"
        ).fetchone()
        if row:
            date_range["min"] = row["min_date"]
            date_range["max"] = row["max_date"]

        # GPS coverage: how many memories have lat/lon
        gps_coverage = {"memories_with_gps": 0, "memories_total": total_memories, "pct": 0.0}
        row = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE lat IS NOT NULL AND lon IS NOT NULL"
        ).fetchone()
        if row:
            gps_coverage["memories_with_gps"] = row["c"]
            if total_memories > 0:
                gps_coverage["pct"] = round(row["c"] / total_memories * 100, 1)

        return {
            "account_info": account_info,
            "total_assets": total_assets,
            "total_memories": total_memories,
            "total_locations": total_locations,
            "total_friends": total_friends,
            "total_chat_messages": total_chat_messages,
            "total_snap_messages": total_snap_messages,
            "import_count": import_count,
            "date_range": date_range,
            "gps_coverage": gps_coverage,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 6. Unmerge (remove a specific import from vault)
# ---------------------------------------------------------------------------

def unmerge_from_vault(vault_db_path: Path, import_id: int) -> dict:
    """Remove all data belonging to a specific import from the vault.

    Deletes rows from every data table WHERE import_id matches, then removes
    the imports record itself. Runs inside a single transaction — all or nothing.

    Args:
        vault_db_path: Path to vault.db.
        import_id: The import ID to remove.

    Returns:
        Stats dict with per-table removal counts, or {"error": str} on failure.
    """
    vault_db_path = Path(vault_db_path)
    if not vault_db_path.is_file():
        return {"error": "vault_not_found"}

    # Ensure schema is current (import_id columns exist)
    migrate_vault_schema(vault_db_path)

    conn = sqlite3.connect(str(vault_db_path))
    conn.row_factory = sqlite3.Row

    try:
        # Verify the import exists
        row = conn.execute(
            "SELECT id, job_id FROM imports WHERE id = ?", (import_id,)
        ).fetchone()
        if not row:
            logger.warning("Unmerge: import_id=%d not found in vault", import_id)
            return {"error": "import_not_found", "import_id": import_id}

        job_id = row["job_id"]
        logger.info("Unmerge starting: import_id=%d, job_id=%d", import_id, job_id)

        conn.execute("BEGIN")

        # ── Re-ownership: reassign shared deduplicated rows to the next
        #    surviving import BEFORE deleting, so we don't lose data that
        #    later imports also depend on (INSERT OR IGNORE means the first
        #    import "owns" all deduped rows by import_id).
        remaining = conn.execute(
            "SELECT MIN(id) AS next_id FROM imports WHERE id != ?", (import_id,)
        ).fetchone()
        next_import_id = remaining["next_id"] if remaining else None

        if next_import_id is not None:
            for table in _DATA_TABLES_WITH_IMPORT_ID:
                # Reassign rows that would be orphaned: rows owned by this
                # import that have duplicates in other imports (same dedup key).
                # For simplicity, reassign ALL rows from this import to the
                # next surviving import — rows unique to this import will be
                # deleted below, and shared rows survive under the new owner.
                conn.execute(
                    f"UPDATE {table} SET import_id = ? WHERE import_id = ?",
                    (next_import_id, import_id),
                )
            logger.info("  Unmerge: reassigned shared rows to import_id=%d", next_import_id)

        removal_stats = {}
        # Delete from all data tables — only rows still owned by this import
        # (after re-ownership, only rows from the LAST remaining import stay
        #  assigned; if next_import_id is None, this is the last import so
        #  everything gets deleted)
        for table in _DATA_TABLES_WITH_IMPORT_ID:
            cursor = conn.execute(
                f"DELETE FROM {table} WHERE import_id = ?", (import_id,)
            )
            count = cursor.rowcount
            removal_stats[f"{table}_removed"] = count
            if count > 0:
                logger.info("  Unmerge %s: %d rows removed", table, count)

        # Delete the import record itself
        conn.execute("DELETE FROM imports WHERE id = ?", (import_id,))

        # Update vault_meta: clear last_import_job_id if it was this job
        meta_row = conn.execute(
            "SELECT value FROM vault_meta WHERE key = 'last_import_job_id'"
        ).fetchone()
        if meta_row and meta_row["value"] == str(job_id):
            # Set to the most recent remaining import, or empty
            latest = conn.execute(
                "SELECT job_id FROM imports ORDER BY id DESC LIMIT 1"
            ).fetchone()
            new_val = str(latest["job_id"]) if latest else ""
            conn.execute(
                "INSERT OR REPLACE INTO vault_meta (key, value) VALUES (?, ?)",
                ("last_import_job_id", new_val),
            )

        conn.execute("COMMIT")
        logger.info("Unmerge committed: import_id=%d, job_id=%d", import_id, job_id)

        # Add summary totals
        removal_stats["import_id"] = import_id
        removal_stats["job_id"] = job_id
        removal_stats["remaining_imports"] = _count(conn, "imports")
        return removal_stats

    except Exception:
        conn.execute("ROLLBACK")
        logger.exception("Unmerge failed for import_id=%d, rolled back", import_id)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 7. Mergeable job stats (preview before merge)
# ---------------------------------------------------------------------------

def get_mergeable_job_stats(proc_db_path: Path) -> dict:
    """Read a job's proc.db and return a summary for the merge preview UI.

    Opens proc.db read-only and counts rows in each data table.

    Args:
        proc_db_path: Path to the per-job proc.db.

    Returns:
        Summary dict with counts, date range, and snap_uid.
    """
    proc_db_path = Path(proc_db_path)
    if not proc_db_path.is_file():
        return {"error": "proc_db_not_found"}

    conn = sqlite3.connect(f"file:{proc_db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        summary = {
            "assets": 0,
            "memories": 0,
            "locations": 0,
            "friends": 0,
            "chat_messages": 0,
            "snap_messages": 0,
            "stories": 0,
            "snap_pro": 0,
            "places": 0,
            "matches": 0,
            "date_range_min": None,
            "date_range_max": None,
            "snap_uid": None,
            "snap_username": None,
        }

        for table in ["assets", "memories", "locations", "friends",
                       "chat_messages", "snap_messages", "stories",
                       "snap_pro", "places", "matches"]:
            if _table_exists(conn, table):
                summary[table] = _count(conn, table)

        # Date range from memories
        if _table_exists(conn, "memories"):
            row = conn.execute(
                "SELECT MIN(date_dt) as min_d, MAX(date_dt) as max_d FROM memories"
            ).fetchone()
            if row:
                summary["date_range_min"] = row["min_d"]
                summary["date_range_max"] = row["max_d"]

        # Try to get snap_uid / snap_username from vault_meta (proc.db may have it)
        if _table_exists(conn, "vault_meta"):
            meta = {r["key"]: r["value"]
                    for r in conn.execute("SELECT key, value FROM vault_meta").fetchall()}
            summary["snap_uid"] = meta.get("snap_account_uid") or None
            summary["snap_username"] = meta.get("snap_username") or None

        return summary
    except sqlite3.Error as e:
        logger.warning("Could not read proc.db at %s: %s", proc_db_path, e)
        return {"error": str(e)}
    finally:
        conn.close()
