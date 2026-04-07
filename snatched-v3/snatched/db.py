import asyncio
import asyncpg
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def get_pool(
    postgres_url: str,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """Create and return an asyncpg connection pool.

    Retries up to 3 times on connection failure (1s delay between retries).

    Args:
        postgres_url: Full DSN, e.g. 'postgresql://user:pass@host:5432/db'
        min_size: Minimum pool connections
        max_size: Maximum pool connections

    Returns:
        asyncpg.Pool ready for queries.

    Raises:
        ConnectionError: If unable to connect after 3 retries.
    """
    max_retries = 3
    retry_delay = 1

    async def _init_connection(conn):
        """Register JSON codec so JSONB columns auto-decode to Python dicts."""
        await conn.set_type_codec(
            'jsonb', encoder=json.dumps, decoder=json.loads,
            schema='pg_catalog',
        )
        await conn.set_type_codec(
            'json', encoder=json.dumps, decoder=json.loads,
            schema='pg_catalog',
        )

    for attempt in range(max_retries):
        try:
            pool = await asyncpg.create_pool(
                postgres_url,
                min_size=min_size,
                max_size=max_size,
                init=_init_connection,
            )
            logger.info("PostgreSQL pool created successfully")
            return pool
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Failed to connect to PostgreSQL (attempt {attempt + 1}/{max_retries}): {e}"
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Failed to connect to PostgreSQL after {max_retries} retries")
                raise ConnectionError(
                    f"Unable to connect to PostgreSQL after {max_retries} retries"
                ) from e


async def init_schema(pool: asyncpg.Pool) -> None:
    """Create all PostgreSQL tables if they don't exist.

    Idempotent — safe to call on every startup.

    Tables created:
    - users
    - processing_jobs
    - job_events
    - user_preferences
    - upload_sessions
    - upload_files
    """
    ddl_statements = [
        # Users table
        """
        CREATE TABLE IF NOT EXISTS users (
            id                   SERIAL PRIMARY KEY,
            username             TEXT UNIQUE NOT NULL,
            email                TEXT,
            display_name         TEXT,
            password_hash        TEXT,
            auth_provider        TEXT NOT NULL DEFAULT 'local',
            external_id          TEXT,
            tier                 TEXT NOT NULL DEFAULT 'free'
                                 CHECK(tier IN ('free', 'pro')),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen            TIMESTAMPTZ,
            storage_quota_bytes  BIGINT NOT NULL DEFAULT 10737418240
        )
        """,
        # Users indexes
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
        "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC)",
        # Processing jobs table
        """
        CREATE TABLE IF NOT EXISTS processing_jobs (
            id                   SERIAL PRIMARY KEY,
            user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status               TEXT NOT NULL DEFAULT 'pending'
                                 CHECK(status IN ('pending', 'queued', 'running', 'scanned', 'matched', 'enriched', 'exporting', 'completed', 'failed', 'cancelled')),
            upload_filename      TEXT,
            upload_size_bytes    BIGINT,
            phases_requested     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            lanes_requested      TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            processing_mode      TEXT NOT NULL DEFAULT 'speed_run'
                                 CHECK(processing_mode IN ('speed_run', 'power_user', 'quick_rescue')),
            progress_pct         INTEGER NOT NULL DEFAULT 0
                                 CHECK(progress_pct >= 0 AND progress_pct <= 100),
            current_phase        TEXT,
            error_message        TEXT,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at           TIMESTAMPTZ,
            completed_at         TIMESTAMPTZ,
            stats_json           JSONB
        )
        """,
        # Processing jobs indexes
        "CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON processing_jobs(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON processing_jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON processing_jobs(created_at DESC)",
        # Job events table
        """
        CREATE TABLE IF NOT EXISTS job_events (
            id           SERIAL PRIMARY KEY,
            job_id       INTEGER NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
            event_type   TEXT NOT NULL,
            message      TEXT,
            data_json    JSONB,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        # Job events indexes
        "CREATE INDEX IF NOT EXISTS idx_events_job_id ON job_events(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_events_created_at ON job_events(created_at DESC)",
        # User preferences table
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            id                 SERIAL PRIMARY KEY,
            user_id            INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            burn_overlays      BOOLEAN DEFAULT true,
            dark_mode_pngs     BOOLEAN DEFAULT false,
            exif_enabled       BOOLEAN DEFAULT true,
            xmp_enabled        BOOLEAN DEFAULT false,
            gps_window_seconds INTEGER DEFAULT 300,
            folder_style       TEXT DEFAULT 'year_month',
            gps_precision      TEXT DEFAULT 'exact',
            hide_sent_to       BOOLEAN DEFAULT false,
            chat_timestamps    BOOLEAN DEFAULT true,
            chat_cover_pages   BOOLEAN DEFAULT true,
            chat_text          BOOLEAN DEFAULT true,
            chat_png           BOOLEAN DEFAULT true,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        # Upload sessions table (for chunked upload)
        """
        CREATE TABLE IF NOT EXISTS upload_sessions (
            id              BIGSERIAL PRIMARY KEY,
            user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_token   TEXT NOT NULL UNIQUE,
            status          TEXT NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active', 'completed', 'expired', 'aborted')),
            file_count      INTEGER NOT NULL,
            total_bytes     BIGINT NOT NULL,
            bytes_received  BIGINT NOT NULL DEFAULT 0,
            options_json    JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at      TIMESTAMPTZ NOT NULL,
            completed_at    TIMESTAMPTZ,
            job_id          BIGINT REFERENCES processing_jobs(id)
        )
        """,
        # Upload sessions indexes
        "CREATE INDEX IF NOT EXISTS idx_upload_sessions_user ON upload_sessions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_upload_sessions_token ON upload_sessions(session_token)",
        "CREATE INDEX IF NOT EXISTS idx_upload_sessions_expires ON upload_sessions(expires_at) WHERE status = 'active'",
        # Upload files table (individual files within a session)
        """
        CREATE TABLE IF NOT EXISTS upload_files (
            id              BIGSERIAL PRIMARY KEY,
            session_id      BIGINT NOT NULL REFERENCES upload_sessions(id) ON DELETE CASCADE,
            file_index      INTEGER NOT NULL,
            filename        TEXT NOT NULL,
            file_size       BIGINT NOT NULL,
            sha256_expected TEXT NOT NULL,
            sha256_actual   TEXT,
            bytes_received  BIGINT NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending', 'uploading', 'verifying', 'complete', 'failed')),
            completed_at    TIMESTAMPTZ,
            UNIQUE(session_id, file_index)
        )
        """,
        # Upload files indexes
        "CREATE INDEX IF NOT EXISTS idx_upload_files_session ON upload_files(session_id)",
    ]

    # P1 Metadata Power Tools tables
    ddl_statements += [
        # Tag edit audit trail
        """
        CREATE TABLE IF NOT EXISTS tag_edits (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id      INTEGER NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
            asset_id    INTEGER NOT NULL,
            file_path   TEXT NOT NULL,
            field_name  TEXT NOT NULL,
            old_value   TEXT,
            new_value   TEXT,
            edit_type   TEXT NOT NULL DEFAULT 'manual'
                        CHECK(edit_type IN ('manual', 'batch', 'preset', 'undo')),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tag_edits_user ON tag_edits(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_tag_edits_asset ON tag_edits(asset_id)",
        "CREATE INDEX IF NOT EXISTS idx_tag_edits_job ON tag_edits(job_id)",

        # Reusable tag presets
        """
        CREATE TABLE IF NOT EXISTS tag_presets (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            description TEXT,
            tags_json   JSONB NOT NULL DEFAULT '{}',
            is_builtin  BOOLEAN NOT NULL DEFAULT false,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tag_presets_user ON tag_presets(user_id)",

        # Custom metadata schemas/namespaces
        """
        CREATE TABLE IF NOT EXISTS custom_schemas (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            namespace_uri    TEXT NOT NULL,
            namespace_prefix TEXT NOT NULL,
            fields_json      JSONB NOT NULL DEFAULT '[]',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, namespace_prefix)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_custom_schemas_user ON custom_schemas(user_id)",
    ]

    # P2 Corrections tables
    ddl_statements += [
        # Saved locations for GPS "snap to known location"
        """
        CREATE TABLE IF NOT EXISTS saved_locations (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            lat         DOUBLE PRECISION NOT NULL,
            lon         DOUBLE PRECISION NOT NULL,
            radius_m    INTEGER NOT NULL DEFAULT 50,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_saved_locations_user ON saved_locations(user_id)",

        # Friend name aliases and merges
        """
        CREATE TABLE IF NOT EXISTS friend_aliases (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            snap_username   TEXT NOT NULL,
            display_name    TEXT NOT NULL,
            merged_with     TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, snap_username)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_friend_aliases_user ON friend_aliases(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_friend_aliases_username ON friend_aliases(snap_username)",

        # Redaction profiles for privacy stripping
        """
        CREATE TABLE IF NOT EXISTS redaction_profiles (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            description     TEXT,
            rules_json      JSONB NOT NULL DEFAULT '[]',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_redaction_profiles_user ON redaction_profiles(user_id)",
    ]

    # P3 Advanced Pipeline Controls tables
    ddl_statements += [
        # Saved pipeline configurations (strategy weights, thresholds, folder patterns, export settings)
        """
        CREATE TABLE IF NOT EXISTS pipeline_configs (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            description      TEXT,
            config_json      JSONB NOT NULL DEFAULT '{}',
            is_default       BOOLEAN NOT NULL DEFAULT false,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_pipeline_configs_user ON pipeline_configs(user_id)",
        # P4: Albums for auto-generated trip clustering and manual collections
        """
        CREATE TABLE IF NOT EXISTS albums (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id           INTEGER REFERENCES processing_jobs(id) ON DELETE SET NULL,
            name             TEXT NOT NULL,
            description      TEXT,
            auto_generated   BOOLEAN NOT NULL DEFAULT false,
            center_lat       DOUBLE PRECISION,
            center_lon       DOUBLE PRECISION,
            location_name    TEXT,
            start_date       TEXT,
            end_date         TEXT,
            item_count       INTEGER NOT NULL DEFAULT 0,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_albums_user ON albums(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_albums_job ON albums(job_id)",
        # P4: Album items linking albums to SQLite asset IDs
        """
        CREATE TABLE IF NOT EXISTS album_items (
            id               SERIAL PRIMARY KEY,
            album_id         INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
            asset_id         INTEGER NOT NULL,
            job_id           INTEGER NOT NULL,
            sort_order       INTEGER NOT NULL DEFAULT 0,
            added_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_album_items_album ON album_items(album_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_album_items_unique ON album_items(album_id, asset_id, job_id)",
        # P6: API access keys for programmatic access
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key_hash         TEXT NOT NULL,
            key_prefix       TEXT NOT NULL,
            name             TEXT NOT NULL DEFAULT 'default',
            scopes           TEXT NOT NULL DEFAULT 'read,write',
            rate_limit_rpm   INTEGER NOT NULL DEFAULT 60,
            last_used_at     TIMESTAMPTZ,
            revoked_at       TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)",
        # P6: Webhook notification endpoints
        """
        CREATE TABLE IF NOT EXISTS webhooks (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            url              TEXT NOT NULL,
            name             TEXT NOT NULL DEFAULT '',
            events           TEXT NOT NULL DEFAULT 'job.completed,job.failed',
            secret           TEXT,
            active           BOOLEAN NOT NULL DEFAULT true,
            last_triggered_at TIMESTAMPTZ,
            last_status_code INTEGER,
            failure_count    INTEGER NOT NULL DEFAULT 0,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_webhooks_user ON webhooks(user_id)",
        # P6: Scheduled/recurring export reminders
        """
        CREATE TABLE IF NOT EXISTS schedules (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            frequency        TEXT NOT NULL DEFAULT 'monthly',
            day_of_month     INTEGER DEFAULT 1,
            day_of_week      INTEGER DEFAULT NULL,
            next_run_at      TIMESTAMPTZ,
            last_run_at      TIMESTAMPTZ,
            active           BOOLEAN NOT NULL DEFAULT true,
            notify_email     BOOLEAN NOT NULL DEFAULT false,
            notify_webhook   BOOLEAN NOT NULL DEFAULT false,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_schedules_user ON schedules(user_id)",
        # Exports table — one row per download bundle requested by the user
        """
        CREATE TABLE IF NOT EXISTS exports (
            id              SERIAL PRIMARY KEY,
            job_id          INTEGER NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
            user_id         INTEGER NOT NULL REFERENCES users(id),
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','building','completed','failed')),
            export_type     TEXT NOT NULL DEFAULT 'full'
                            CHECK(export_type IN ('quick_rescue','full','free','rescue')),
            lanes           TEXT[] NOT NULL DEFAULT '{memories}',
            exif_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
            xmp_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
            burn_overlays   BOOLEAN NOT NULL DEFAULT TRUE,
            chat_text       BOOLEAN NOT NULL DEFAULT TRUE,
            chat_png        BOOLEAN NOT NULL DEFAULT TRUE,
            dark_mode_pngs  BOOLEAN NOT NULL DEFAULT FALSE,
            folder_style    TEXT NOT NULL DEFAULT 'year_month',
            gps_precision   TEXT NOT NULL DEFAULT 'exact',
            hide_sent_to    BOOLEAN NOT NULL DEFAULT FALSE,
            chat_timestamps BOOLEAN NOT NULL DEFAULT TRUE,
            chat_cover_pages BOOLEAN NOT NULL DEFAULT TRUE,
            zip_dir         TEXT,
            zip_part_count  INTEGER DEFAULT 1,
            zip_total_bytes BIGINT,
            file_count      INTEGER,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ,
            error_message   TEXT,
            stats_json      JSONB
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_exports_job ON exports(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_exports_user ON exports(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_exports_status ON exports(status)",
    ]

    # Centralized tier plans — single source of truth for all tier limits
    ddl_statements += [
        """
        CREATE TABLE IF NOT EXISTS tier_plans (
            id                      SERIAL PRIMARY KEY,
            tier_key                TEXT UNIQUE NOT NULL,
            label                   TEXT NOT NULL,
            color                   TEXT NOT NULL,
            sort_order              INTEGER NOT NULL DEFAULT 0,
            storage_gb              INTEGER,
            max_upload_bytes        BIGINT,
            max_upload_label        TEXT,
            retention_days          INTEGER,
            concurrent_jobs         INTEGER NOT NULL DEFAULT 1,
            bulk_upload             BOOLEAN NOT NULL DEFAULT false,
            max_api_keys            INTEGER NOT NULL DEFAULT 0,
            api_key_rate_limit_rpm  INTEGER NOT NULL DEFAULT 0,
            max_webhooks            INTEGER NOT NULL DEFAULT 0,
            max_schedules           INTEGER NOT NULL DEFAULT 0,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tier_plans_meta (
            id       INTEGER PRIMARY KEY DEFAULT 1,
            version  INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT tier_plans_meta_single_row CHECK (id = 1)
        )
        """,
        """
        INSERT INTO tier_plans_meta (id, version) VALUES (1, 1) ON CONFLICT DO NOTHING
        """,
        """
        CREATE TABLE IF NOT EXISTS system_config (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            value_type  TEXT NOT NULL DEFAULT 'text'
                        CHECK(value_type IN ('integer', 'boolean', 'text')),
            description TEXT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ]

    # Vault system — persistent per-Snapchat-account data accumulation
    ddl_statements += [
        """
        CREATE TABLE IF NOT EXISTS vaults (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            snap_account_uid    TEXT,
            snap_username       TEXT,
            vault_path          TEXT NOT NULL,
            import_count        INTEGER NOT NULL DEFAULT 0,
            total_assets        INTEGER NOT NULL DEFAULT 0,
            total_locations     INTEGER NOT NULL DEFAULT 0,
            total_friends       INTEGER NOT NULL DEFAULT 0,
            stats_json          JSONB,
            last_import_at      TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_vaults_account
            ON vaults(user_id, COALESCE(snap_account_uid, snap_username, ''))
        """,
        "CREATE INDEX IF NOT EXISTS idx_vaults_user ON vaults(user_id)",
        """
        CREATE TABLE IF NOT EXISTS vault_imports (
            id                  SERIAL PRIMARY KEY,
            vault_id            INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
            job_id              INTEGER REFERENCES processing_jobs(id) ON DELETE SET NULL,
            original_filename   TEXT,
            import_type         TEXT NOT NULL DEFAULT 'full',
            assets_added        INTEGER NOT NULL DEFAULT 0,
            assets_skipped      INTEGER NOT NULL DEFAULT 0,
            locations_added     INTEGER NOT NULL DEFAULT 0,
            friends_added       INTEGER NOT NULL DEFAULT 0,
            gps_rematched       INTEGER NOT NULL DEFAULT 0,
            sqlite_import_id    INTEGER,
            stats_json          JSONB,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_vault_imports_vault ON vault_imports(vault_id)",
        "CREATE INDEX IF NOT EXISTS idx_vault_imports_job ON vault_imports(job_id)",
    ]

    # Migrations for existing tables (idempotent — safe to run every startup)
    migrations = [
        # Add options_json to upload_sessions (v3.1)
        """
        ALTER TABLE upload_sessions ADD COLUMN IF NOT EXISTS options_json JSONB NOT NULL DEFAULT '{}'
        """,
        # P3: Add match threshold to user_preferences
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS match_confidence_min REAL DEFAULT 0.0
        """,
        # P3: Add strategy weights JSON to user_preferences
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS strategy_weights_json JSONB DEFAULT NULL
        """,
        # P3: Add folder pattern to user_preferences
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS folder_pattern TEXT DEFAULT '{YYYY}/{MM}'
        """,
        # P3: Add export format settings to user_preferences
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS export_settings_json JSONB DEFAULT NULL
        """,
        # P5: Add tier to users (free/pro)
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'free'
        """,
        # Normalize stale tier values to 'free' before adding CHECK
        """
        UPDATE users SET tier = 'free' WHERE tier NOT IN ('free', 'pro')
        """,
        # P5: Add retention expiry to processing_jobs
        """
        ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS retention_expires_at TIMESTAMPTZ DEFAULT NULL
        """,
        # P5: Add job group ID for bulk upload linking
        """
        ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS job_group_id TEXT DEFAULT NULL
        """,
        # Auth: Add auth columns to users table
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT
        """,
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT
        """,
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'local'
        """,
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS external_id TEXT
        """,
        # Living Canvas: add matched/enriched statuses to processing_jobs
        # DROP + ADD the constraint because PostgreSQL cannot ALTER a CHECK in-place.
        # Wrapped in a DO block so it's a no-op if the constraint was already updated.
        """
        DO $$ BEGIN
            ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS processing_jobs_status_check;
            ALTER TABLE processing_jobs ADD CONSTRAINT processing_jobs_status_check
                CHECK(status IN ('pending', 'queued', 'running', 'scanned', 'matched', 'enriched', 'exporting', 'completed', 'failed', 'cancelled'));
        EXCEPTION WHEN others THEN NULL;
        END $$
        """,
        # Living Canvas: add processing_mode column (speed_run | power_user)
        # EXCEPTION guard makes this idempotent — safe to run on every startup.
        """
        DO $$ BEGIN
            ALTER TABLE processing_jobs ADD COLUMN processing_mode TEXT NOT NULL DEFAULT 'speed_run'
                CHECK(processing_mode IN ('speed_run', 'power_user', 'quick_rescue'));
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$
        """,
        # WU-5: Add relative_path to upload_files for preserving zip directory structure
        """
        ALTER TABLE upload_files ADD COLUMN IF NOT EXISTS relative_path TEXT
        """,
        # Update processing_mode CHECK constraint to include quick_rescue.
        # The ADD COLUMN migration above handles new installs; this handles
        # existing DBs where the column was created with the old constraint.
        """
        DO $$ BEGIN
            ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS processing_jobs_processing_mode_check;
            ALTER TABLE processing_jobs ADD CONSTRAINT processing_jobs_processing_mode_check
                CHECK (processing_mode IN ('speed_run', 'power_user', 'quick_rescue'));
        END $$
        """,
        # WU-17: Add is_admin flag to users table for admin-gated features
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE
        """,
        # B-2: Add dark_mode_pngs to exports table for per-export chat rendering mode
        """
        ALTER TABLE exports ADD COLUMN IF NOT EXISTS dark_mode_pngs BOOLEAN NOT NULL DEFAULT FALSE
        """,
        # New toggles: folder_style, gps_precision, hide_sent_to, chat_timestamps, chat_cover_pages
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS folder_style TEXT DEFAULT 'year_month'
        """,
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS gps_precision TEXT DEFAULT 'exact'
        """,
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS hide_sent_to BOOLEAN DEFAULT false
        """,
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS chat_timestamps BOOLEAN DEFAULT true
        """,
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS chat_cover_pages BOOLEAN DEFAULT true
        """,
        """
        ALTER TABLE exports ADD COLUMN IF NOT EXISTS folder_style TEXT NOT NULL DEFAULT 'year_month'
        """,
        """
        ALTER TABLE exports ADD COLUMN IF NOT EXISTS gps_precision TEXT NOT NULL DEFAULT 'exact'
        """,
        """
        ALTER TABLE exports ADD COLUMN IF NOT EXISTS hide_sent_to BOOLEAN NOT NULL DEFAULT FALSE
        """,
        """
        ALTER TABLE exports ADD COLUMN IF NOT EXISTS chat_timestamps BOOLEAN NOT NULL DEFAULT TRUE
        """,
        """
        ALTER TABLE exports ADD COLUMN IF NOT EXISTS chat_cover_pages BOOLEAN NOT NULL DEFAULT TRUE
        """,
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS chat_text BOOLEAN DEFAULT true
        """,
        """
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS chat_png BOOLEAN DEFAULT true
        """,
        # Vault: Add account fingerprint columns to processing_jobs
        """
        ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS snap_account_uid TEXT
        """,
        """
        ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS snap_username TEXT
        """,
        """
        ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS original_filename TEXT
        """,
        "CREATE INDEX IF NOT EXISTS idx_jobs_snap_uid ON processing_jobs(snap_account_uid)",
        # Vault: Store SQLite import_id so unmerge works even after job deletion (job_id → NULL)
        """
        ALTER TABLE vault_imports ADD COLUMN IF NOT EXISTS sqlite_import_id INTEGER
        """,
        # Monetization: per-job tier and payment tracking
        """
        ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS job_tier TEXT NOT NULL DEFAULT 'free'
        """,
        """
        ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'unpaid'
        """,
        """
        ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS payment_intent_id TEXT
        """,
        """
        ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS add_ons JSONB NOT NULL DEFAULT '[]'::JSONB
        """,
        # Monetization: update exports CHECK constraint to allow free/rescue export types
        """
        DO $$ BEGIN
            ALTER TABLE exports DROP CONSTRAINT IF EXISTS exports_export_type_check;
            ALTER TABLE exports ADD CONSTRAINT exports_export_type_check
                CHECK (export_type IN ('quick_rescue', 'full', 'free', 'rescue'));
        EXCEPTION WHEN others THEN NULL;
        END $$
        """,
    ]

    async with pool.acquire() as conn:
        # Advisory lock prevents race when multiple uvicorn workers start simultaneously
        await conn.execute("SELECT pg_advisory_lock(1)")
        try:
            for statement in ddl_statements:
                await conn.execute(statement)
            for migration in migrations:
                try:
                    await conn.execute(migration)
                except Exception:
                    pass  # Column already exists or other idempotent failure
        finally:
            await conn.execute("SELECT pg_advisory_unlock(1)")

    logger.info("PostgreSQL schema initialized successfully")


async def create_user(
    pool: asyncpg.Pool,
    username: str,
    display_name: str | None = None,
    storage_quota_bytes: int = 10 * 1024 * 1024 * 1024,
) -> int:
    """Create a new user. Return user_id.

    Args:
        pool: asyncpg connection pool
        username: Unique username (from Authelia X-Remote-User header)
        display_name: Optional display name
        storage_quota_bytes: Storage limit in bytes (default 10 GB)

    Returns:
        int: New user ID.

    Raises:
        asyncpg.UniqueViolationError: If username already exists.
    """
    query = """
    INSERT INTO users (username, display_name, storage_quota_bytes)
    VALUES ($1, $2, $3)
    RETURNING id
    """
    row = await pool.fetchrow(query, username, display_name, storage_quota_bytes)
    user_id = row["id"]
    logger.info(f"Created user {user_id} with username '{username}'")
    return user_id


async def get_or_create_user(
    pool: asyncpg.Pool,
    username: str,
    display_name: str | None = None,
) -> int:
    """Get user_id for username, creating the user if not found.

    Used on every authenticated request to auto-provision users.

    Args:
        pool: asyncpg connection pool
        username: Username from Authelia header
        display_name: Optional display name (used only on creation)

    Returns:
        int: User ID (existing or newly created).
    """
    query = """
    INSERT INTO users (username, display_name)
    VALUES ($1, $2)
    ON CONFLICT (username) DO UPDATE SET last_seen = NOW()
    RETURNING id
    """
    row = await pool.fetchrow(query, username, display_name)
    user_id = row["id"]
    logger.debug(f"Got or created user {user_id} for username '{username}'")
    return user_id


async def update_job(
    pool: asyncpg.Pool,
    job_id: int,
    status: str | None = None,
    current_phase: str | None = None,
    progress_pct: int | None = None,
    error_message: str | None = None,
    stats_json: dict | None = None,
) -> None:
    """Update job fields. None values are skipped (no UPDATE for that column).

    Auto-behavior:
    - Sets started_at = NOW() on first transition away from 'pending'
    - Sets completed_at = NOW() when status becomes 'completed' or 'failed'

    Args:
        pool: asyncpg connection pool
        job_id: Job to update
        status: New status ('pending', 'running', 'completed', 'failed')
        current_phase: Currently executing phase name
        progress_pct: Integer 0–100
        error_message: Error description if status='failed'
        stats_json: Final stats dict (serialized to JSONB)
    """
    # Build dynamic SET clause
    set_clauses = []
    params = []
    param_idx = 1

    if status is not None:
        set_clauses.append(f"status = ${param_idx}")
        params.append(status)
        param_idx += 1

    if current_phase is not None:
        set_clauses.append(f"current_phase = ${param_idx}")
        params.append(current_phase)
        param_idx += 1

    if progress_pct is not None:
        set_clauses.append(f"progress_pct = ${param_idx}")
        params.append(progress_pct)
        param_idx += 1

    if error_message is not None:
        set_clauses.append(f"error_message = ${param_idx}")
        params.append(error_message)
        param_idx += 1

    if stats_json is not None:
        set_clauses.append(f"stats_json = ${param_idx}")
        params.append(stats_json)
        param_idx += 1

    # Auto-set started_at on first transition away from 'pending'
    if status is not None and status != "pending":
        set_clauses.append(f"started_at = COALESCE(started_at, NOW())")

    # Auto-set completed_at when status becomes 'completed' or 'failed'
    if status in ("completed", "failed"):
        set_clauses.append("completed_at = NOW()")

    if not set_clauses:
        # Nothing to update
        logger.debug(f"No fields to update for job {job_id}")
        return

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE processing_jobs SET {set_clause_str} WHERE id = ${param_idx}"
    params.append(job_id)

    await pool.execute(query, *params)
    logger.debug(f"Updated job {job_id}: status={status}, phase={current_phase}")


async def emit_event(
    pool: asyncpg.Pool,
    job_id: int,
    event_type: str,
    message: str | None = None,
    data_json: dict | None = None,
) -> int:
    """Log an event for a job. Return event_id.

    Event types used by the pipeline:
    - 'phase_start' — phase is beginning
    - 'progress' — progress percentage update
    - 'scanned' — ingest scan complete (Living Canvas pause)
    - 'matched' — match complete (Living Canvas pause)
    - 'enriched' — enrichment complete (Living Canvas pause)
    - 'error' — fatal error, job will fail
    - 'complete' — entire job finished
    - 'cancelled' — job was cancelled

    Args:
        pool: asyncpg connection pool
        job_id: Job this event belongs to
        event_type: Event category string
        message: Human-readable description
        data_json: Optional structured data dict

    Returns:
        int: New event ID.
    """
    query = """
    INSERT INTO job_events (job_id, event_type, message, data_json)
    VALUES ($1, $2, $3, $4::jsonb)
    RETURNING id
    """
    # The asyncpg JSONB codec (registered in get_pool) calls json.dumps
    # automatically.  Pass the dict directly — do NOT pre-serialize or the
    # value will be double-encoded.
    row = await pool.fetchrow(query, job_id, event_type, message, data_json)
    event_id = row["id"]
    logger.debug(f"Emitted event {event_id} for job {job_id}: {event_type}")
    return event_id


async def get_events_after(
    pool: asyncpg.Pool,
    job_id: int,
    after_event_id: int,
) -> list[dict]:
    """Get all events for a job after a given event_id.

    Used by the SSE endpoint to stream events to the browser.

    Args:
        pool: asyncpg connection pool
        job_id: Job to query
        after_event_id: Return only events with id > this value (0 = all)

    Returns:
        List of event dicts: [
            {
                'id': int,
                'event_type': str,
                'message': str | None,
                'data_json': dict | None,
                'created_at': datetime,
            },
            ...
        ]
    """
    query = """
    SELECT id, event_type, message, data_json, created_at
    FROM job_events
    WHERE job_id = $1 AND id > $2
    ORDER BY id ASC
    """
    rows = await pool.fetch(query, job_id, after_event_id)

    events = []
    for row in rows:
        event = {
            "id": row["id"],
            "event_type": row["event_type"],
            "message": row["message"],
            "data_json": row["data_json"],  # asyncpg returns JSONB as dict automatically
            "created_at": row["created_at"],
        }
        events.append(event)

    logger.debug(f"Retrieved {len(events)} events for job {job_id} after event {after_event_id}")
    return events


BUILTIN_PRESETS = [
    {
        "name": "Photo Library Import",
        "description": "Marks files as imported from Snapchat export via Snatched.",
        "tags_json": {
            "EXIF:Software": "Snatched v3",
            "XMP:Creator": "Snapchat Export",
        },
    },
    {
        "name": "Archival",
        "description": "Full archival tagging: software, rights, creator, and source.",
        "tags_json": {
            "EXIF:Software": "Snatched v3",
            "XMP:Rights": "Personal Archive",
            "XMP:Creator": "Snapchat Export",
            "IPTC:Source": "Snapchat",
        },
    },
    {
        "name": "Social Media",
        "description": "Adds a description noting recovery from Snapchat export.",
        "tags_json": {
            "EXIF:Software": "Snatched v3",
            "XMP:Description": "Recovered from Snapchat export",
        },
    },
]


async def seed_builtin_presets(pool: asyncpg.Pool) -> None:
    """Seed built-in tag presets if none exist.

    Idempotent — only inserts if no is_builtin=true rows are present.
    Uses an advisory lock so only one worker runs the seed.
    """
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock(2)")
        try:
            existing = await conn.fetchval(
                "SELECT COUNT(*) FROM tag_presets WHERE is_builtin = true"
            )
            if existing == 0:
                for preset in BUILTIN_PRESETS:
                    tags_str = json.dumps(preset["tags_json"])
                    await conn.execute(
                        """
                        INSERT INTO tag_presets (user_id, name, description, tags_json, is_builtin)
                        VALUES (NULL, $1, $2, $3::JSONB, true)
                        """,
                        preset["name"],
                        preset["description"],
                        tags_str,
                    )
                logger.info(f"Seeded {len(BUILTIN_PRESETS)} built-in tag presets")
            else:
                logger.debug(f"Built-in presets already seeded ({existing} found)")
        finally:
            await conn.execute("SELECT pg_advisory_unlock(2)")


async def seed_tier_plans(pool: asyncpg.Pool) -> None:
    """Seed default tier plans and system config if not present.

    Idempotent — only inserts if no tier_plans rows exist.
    Uses advisory lock so only one worker runs the seed.
    """
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock(3)")
        try:
            existing = await conn.fetchval(
                "SELECT COUNT(*) FROM tier_plans"
            )
            if existing == 0:
                # Seed Free tier
                await conn.execute(
                    """
                    INSERT INTO tier_plans
                        (tier_key, label, color, sort_order, storage_gb,
                         max_upload_bytes, max_upload_label, retention_days,
                         concurrent_jobs, bulk_upload,
                         max_api_keys, api_key_rate_limit_rpm,
                         max_webhooks, max_schedules)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    "free", "Free", "var(--text-muted)", 0,
                    10, 5 * 1024 ** 3, "5 GB", 30,
                    1, False,
                    0, 0, 0, 0,
                )
                # Seed Pro tier
                await conn.execute(
                    """
                    INSERT INTO tier_plans
                        (tier_key, label, color, sort_order, storage_gb,
                         max_upload_bytes, max_upload_label, retention_days,
                         concurrent_jobs, bulk_upload,
                         max_api_keys, api_key_rate_limit_rpm,
                         max_webhooks, max_schedules)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    "pro", "Pro", "var(--snap-yellow)", 1,
                    50, 25 * 1024 ** 3, "25 GB", 180,
                    1, True,
                    3, 60, 3, 2,
                )
                logger.info("Seeded 2 default tier plans (free, pro)")
            else:
                logger.debug(f"Tier plans already seeded ({existing} found)")

            # Seed system_config defaults (each row individually, skip if exists)
            defaults = [
                ("max_global_concurrent_jobs", "4", "integer",
                 "Max running jobs across ALL users"),
                ("max_global_storage_gb", "500", "integer",
                 "Total storage cap across all users"),
                ("registration_mode", "open", "text",
                 "open / invite_only / closed"),
                ("max_uploads_per_hour", "10", "integer",
                 "Per-user upload rate limit"),
                ("stats_baseline_files", "0", "integer",
                 "Baseline offset for 'memories rescued' on landing page"),
                ("stats_baseline_gps", "0", "integer",
                 "Baseline offset for 'locations restored' on landing page"),
                ("stats_baseline_users", "0", "integer",
                 "Baseline offset for 'users served' on landing page"),
            ]
            for key, value, vtype, desc in defaults:
                await conn.execute(
                    """
                    INSERT INTO system_config (key, value, value_type, description)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (key) DO NOTHING
                    """,
                    key, value, vtype, desc,
                )
            logger.debug("System config defaults seeded")
        finally:
            await conn.execute("SELECT pg_advisory_unlock(3)")


async def get_user_jobs(
    pool: asyncpg.Pool,
    user_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Get jobs for a user, most recent first.

    Args:
        pool: asyncpg connection pool
        user_id: Filter to this user
        limit: Max results
        offset: Pagination offset

    Returns:
        List of job dicts: [
            {
                'id': int,
                'status': str,
                'upload_filename': str,
                'upload_size_bytes': int,
                'progress_pct': int,
                'current_phase': str | None,
                'created_at': datetime,
                'started_at': datetime | None,
                'completed_at': datetime | None,
                'stats_json': dict | None,
            },
            ...
        ]
    """
    query = """
    SELECT
        id, status, upload_filename, upload_size_bytes, progress_pct, current_phase,
        created_at, started_at, completed_at, stats_json
    FROM processing_jobs
    WHERE user_id = $1
    ORDER BY created_at DESC
    LIMIT $2
    OFFSET $3
    """
    rows = await pool.fetch(query, user_id, limit, offset)

    jobs = []
    for row in rows:
        job = {
            "id": row["id"],
            "status": row["status"],
            "upload_filename": row["upload_filename"],
            "upload_size_bytes": row["upload_size_bytes"],
            "progress_pct": row["progress_pct"],
            "current_phase": row["current_phase"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "stats_json": row["stats_json"],  # asyncpg returns JSONB as dict automatically
        }
        jobs.append(job)

    logger.debug(f"Retrieved {len(jobs)} jobs for user {user_id}")
    return jobs


# ---------------------------------------------------------------------------
# Export CRUD helpers
# ---------------------------------------------------------------------------

async def create_export(pool, job_id: int, user_id: int, export_type: str = "full",
                        lanes: list = None, exif_enabled: bool = True,
                        xmp_enabled: bool = False, burn_overlays: bool = True,
                        chat_text: bool = True, chat_png: bool = True,
                        dark_mode_pngs: bool = False,
                        folder_style: str = "year_month",
                        gps_precision: str = "exact",
                        hide_sent_to: bool = False,
                        chat_timestamps: bool = True,
                        chat_cover_pages: bool = True) -> int:
    """Create a new export record. Returns export_id."""
    if lanes is None:
        lanes = ["memories"]
    async with pool.acquire() as conn:
        return await conn.fetchval("""
            INSERT INTO exports (job_id, user_id, export_type, lanes,
                                 exif_enabled, xmp_enabled, burn_overlays,
                                 chat_text, chat_png, dark_mode_pngs,
                                 folder_style, gps_precision, hide_sent_to,
                                 chat_timestamps, chat_cover_pages)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15)
            RETURNING id
        """, job_id, user_id, export_type, lanes,
            exif_enabled, xmp_enabled, burn_overlays, chat_text, chat_png,
            dark_mode_pngs, folder_style, gps_precision, hide_sent_to,
            chat_timestamps, chat_cover_pages)


async def get_export(pool, export_id: int) -> dict:
    """Get a single export record by ID."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM exports WHERE id = $1", export_id)
        return dict(row) if row else None


async def list_exports(pool, job_id: int) -> list:
    """List all exports for a job, ordered by creation time."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM exports WHERE job_id = $1 ORDER BY created_at", job_id)
        return [dict(r) for r in rows]


async def update_export(pool, export_id: int, **kwargs) -> None:
    """Update export fields. Accepts any column name as keyword argument."""
    if not kwargs:
        return
    sets = []
    vals = []
    for i, (k, v) in enumerate(kwargs.items(), 1):
        sets.append(f"{k} = ${i}")
        vals.append(v)
    vals.append(export_id)
    query = f"UPDATE exports SET {', '.join(sets)} WHERE id = ${len(vals)}"
    async with pool.acquire() as conn:
        await conn.execute(query, *vals)


async def delete_export(pool, export_id: int) -> None:
    """Delete an export record."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM exports WHERE id = $1", export_id)
