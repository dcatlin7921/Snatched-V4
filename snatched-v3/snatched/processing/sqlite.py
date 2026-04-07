import sqlite3
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BATCH_SIZE: int = 500


def open_database(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the per-user SQLite processing database.

    Creates parent directories if they don't exist.
    Applies schema.sql (idempotent — uses CREATE TABLE IF NOT EXISTS).
    Runs v2→v3 migrations for databases created by older versions.

    Args:
        db_path: Path to SQLite file. Use Path(':memory:') for testing.

    Returns:
        sqlite3.Connection with WAL mode, foreign keys enabled, row_factory set.

    Raises:
        sqlite3.Error: If DB cannot be opened or schema cannot be applied.
    """
    db_path = Path(db_path)
    if str(db_path) != ':memory:':
        db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        db = sqlite3.connect(str(db_path), check_same_thread=False)
        db.row_factory = sqlite3.Row

        # Apply WAL mode and foreign keys explicitly
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA foreign_keys = ON")

        create_schema(db)
        migrate_schema(db)

        logger.info(f"Database opened: {db_path}")
        return db
    except sqlite3.Error as e:
        logger.error(f"Failed to open database at {db_path}: {e}")
        raise


def create_schema(db: sqlite3.Connection) -> list[str]:
    """Execute full schema.sql, creating all 12 core tables + 2 v3 tables.

    Idempotent — uses CREATE TABLE IF NOT EXISTS.

    Returns:
        List of table names that exist after creation (for verification).
    """
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    db.executescript(schema_sql)
    db.commit()

    # Verify tables
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    logger.info(f"Schema created with {len(tables)} tables: {', '.join(tables)}")

    # Log index count
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
    indexes = [row[0] for row in cursor.fetchall()]
    custom = [i for i in indexes if i.startswith('idx_')]
    logger.info(f"{len(custom)} custom indexes created")

    return tables


def migrate_schema(db: sqlite3.Connection) -> None:
    """Apply v2→v3 schema migrations for databases created by older versions.

    Migrations applied (all idempotent — safe to run multiple times):
    - ALTER TABLE matches ADD COLUMN lane TEXT DEFAULT 'memories'
    - ALTER TABLE assets ADD COLUMN xmp_written BOOLEAN DEFAULT 0
    - ALTER TABLE assets ADD COLUMN xmp_path TEXT
    - CREATE TABLE IF NOT EXISTS reprocess_log (...)
    - CREATE TABLE IF NOT EXISTS lane_config (...)

    Uses try/except around each ALTER to skip columns that already exist.
    (SQLite does not support IF NOT EXISTS on ALTER TABLE ADD COLUMN.)
    """
    migrations = [
        ("matches", "lane", "TEXT DEFAULT 'memories'"),
        ("assets", "xmp_written", "BOOLEAN DEFAULT 0"),
        ("assets", "xmp_path", "TEXT"),
        ("assets", "duplicate_of", "INTEGER DEFAULT NULL"),
    ]

    for table, column, definition in migrations:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info(f"Migration applied: ALTER TABLE {table} ADD COLUMN {column}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Create v3 tables if they don't exist (idempotent — also in schema.sql)
    db.execute("""
        CREATE TABLE IF NOT EXISTS reprocess_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
            phases          TEXT,
            lanes           TEXT,
            triggered_by    TEXT,
            status          TEXT DEFAULT 'pending',
            result_json     TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS lane_config (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lane_name       TEXT UNIQUE NOT NULL,
            config_json     TEXT
        )
    """)

    db.commit()


def batch_insert(
    db: sqlite3.Connection,
    table: str,
    columns: list[str],
    rows: list[tuple],
    batch_size: int = BATCH_SIZE,
) -> int:
    """Bulk insert rows into a table with per-batch commits.

    IMPORTANT: `table` and `columns` are used directly in SQL — callers must
    pass only trusted constant values, never user-controlled input.

    Args:
        db: SQLite connection
        table: Table name (must be a trusted constant)
        columns: Column names (must be trusted constants)
        rows: List of value tuples to insert
        batch_size: Rows per commit (default 500)

    Returns:
        Total rows inserted.
    """
    if not rows:
        return 0

    placeholders = ", ".join(["?" for _ in columns])
    col_list = ", ".join(columns)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    total_inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        db.executemany(sql, batch)
        db.commit()
        total_inserted += len(batch)

    logger.info(f"Inserted {total_inserted} rows into {table}")
    return total_inserted


def batch_update(
    db: sqlite3.Connection,
    sql: str,
    rows: list[tuple],
    batch_size: int = BATCH_SIZE,
) -> int:
    """Execute a parameterized UPDATE/INSERT on multiple row tuples with batching.

    Args:
        db: SQLite connection
        sql: Parameterized SQL template (e.g., "UPDATE assets SET x=? WHERE id=?")
        rows: List of parameter tuples
        batch_size: Rows per commit (default 500)

    Returns:
        Total rows affected.
    """
    if not rows:
        return 0

    total_affected = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        db.executemany(sql, batch)
        db.commit()
        total_affected += len(batch)

    logger.info(f"Updated {total_affected} rows with SQL: {sql[:60]}...")
    return total_affected


def log_run(
    db: sqlite3.Connection,
    version: str,
    person: str,
    input_path: str,
    status: str = "running",
    stats: dict | None = None,
) -> int:
    """Insert a run_log entry and return the new row ID.

    Args:
        db: SQLite connection
        version: Snatched version string (e.g., "3.0")
        person: Username running the pipeline
        input_path: Path to the input export directory
        status: Initial status ('running')
        stats: Optional initial stats dict (serialized to JSON)

    Returns:
        run_log row ID.
    """
    flags_json = json.dumps(stats) if stats else None

    cursor = db.execute(
        """
        INSERT INTO run_log (version, person, input_path, status, flags_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (version, person, input_path, status, flags_json)
    )
    db.commit()

    run_id = cursor.lastrowid
    logger.info(f"Log run created: id={run_id}, version={version}, person={person}, status={status}")
    return run_id


def update_run(
    db: sqlite3.Connection,
    run_id: int,
    phase: str | None = None,
    status: str | None = None,
    total_assets: int | None = None,
    total_matched: int | None = None,
    total_exif_ok: int | None = None,
    total_exif_err: int | None = None,
    total_copied: int | None = None,
    elapsed_seconds: float | None = None,
    error_message: str | None = None,
) -> None:
    """Update a run_log entry. None values are skipped (no UPDATE for that column).

    Auto-sets finished_at = datetime('now') when status becomes 'completed' or 'failed'.

    Args:
        db: SQLite connection
        run_id: run_log row ID to update
        phase: Current phase name
        status: New status ('running', 'completed', 'failed')
        total_assets: Total assets discovered
        total_matched: Total assets matched
        total_exif_ok: EXIF writes succeeded
        total_exif_err: EXIF writes failed
        total_copied: Files copied to output
        elapsed_seconds: Total elapsed time
        error_message: Error description if failed
    """
    set_clauses = []
    params = []

    if phase is not None:
        set_clauses.append("phase = ?")
        params.append(phase)

    if status is not None:
        set_clauses.append("status = ?")
        params.append(status)

    if total_assets is not None:
        set_clauses.append("total_assets = ?")
        params.append(total_assets)

    if total_matched is not None:
        set_clauses.append("total_matched = ?")
        params.append(total_matched)

    if total_exif_ok is not None:
        set_clauses.append("total_exif_ok = ?")
        params.append(total_exif_ok)

    if total_exif_err is not None:
        set_clauses.append("total_exif_err = ?")
        params.append(total_exif_err)

    if total_copied is not None:
        set_clauses.append("total_copied = ?")
        params.append(total_copied)

    if elapsed_seconds is not None:
        set_clauses.append("elapsed_seconds = ?")
        params.append(elapsed_seconds)

    if error_message is not None:
        set_clauses.append("error_message = ?")
        params.append(error_message)

    if status in ('completed', 'failed'):
        set_clauses.append("finished_at = datetime('now')")

    if not set_clauses:
        logger.warning(f"update_run: no columns to update for run_id={run_id}")
        return

    params.append(run_id)
    sql = f"UPDATE run_log SET {', '.join(set_clauses)} WHERE id = ?"

    db.execute(sql, params)
    db.commit()

    logger.info(f"Run updated: id={run_id}, status={status}, phase={phase}")
