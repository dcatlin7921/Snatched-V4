-- Pragmas for performance and safety
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- ── ASSETS: Every media file discovered on disk ───────────────────────────────
CREATE TABLE IF NOT EXISTS assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    date_str        TEXT,
    file_id         TEXT,
    ext             TEXT NOT NULL,
    real_ext        TEXT,
    asset_type      TEXT NOT NULL
                    CHECK(asset_type IN ('memory_main', 'memory_overlay', 'chat',
                                        'chat_overlay', 'chat_thumbnail', 'story')),
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
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_assets_file_id     ON assets(file_id);
CREATE INDEX IF NOT EXISTS idx_assets_memory_uuid ON assets(memory_uuid);
CREATE INDEX IF NOT EXISTS idx_assets_date_str    ON assets(date_str);
CREATE INDEX IF NOT EXISTS idx_assets_asset_type  ON assets(asset_type);

-- ── CHAT_MESSAGES: Every message from chat_history.json ───────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    from_user       TEXT,
    media_type      TEXT,
    media_ids       TEXT,
    content         TEXT,
    created         TEXT,
    created_ms      INTEGER,
    is_sender       BOOLEAN DEFAULT 0,
    conversation_title TEXT,
    created_dt      TEXT,
    created_date    TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_media_ids    ON chat_messages(media_ids);
CREATE INDEX IF NOT EXISTS idx_chat_created_date ON chat_messages(created_date);
CREATE INDEX IF NOT EXISTS idx_chat_conversation ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chat_media_type   ON chat_messages(media_type);

-- ── CHAT_MEDIA_IDS: Exploded pipe-separated media IDs ─────────────────────────
CREATE TABLE IF NOT EXISTS chat_media_ids (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_message_id INTEGER NOT NULL REFERENCES chat_messages(id),
    media_id        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_mid ON chat_media_ids(media_id);

-- ── SNAP_MESSAGES: Every entry from snap_history.json ─────────────────────────
CREATE TABLE IF NOT EXISTS snap_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    from_user       TEXT,
    media_type      TEXT,
    created         TEXT,
    created_ms      INTEGER,
    is_sender       BOOLEAN DEFAULT 0,
    conversation_title TEXT,
    created_dt      TEXT,
    created_date    TEXT,
    dedup_key       TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_snap_created_date  ON snap_messages(created_date);
CREATE INDEX IF NOT EXISTS idx_snap_media_type    ON snap_messages(media_type);
CREATE INDEX IF NOT EXISTS idx_snap_date_type     ON snap_messages(created_date, media_type);
CREATE INDEX IF NOT EXISTS idx_snap_conversation  ON snap_messages(conversation_id);

-- ── MEMORIES: All entries from memories_history.json ──────────────────────────
CREATE TABLE IF NOT EXISTS memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mid             TEXT UNIQUE,
    date            TEXT,
    date_dt         TEXT,
    media_type      TEXT,
    location_raw    TEXT,
    lat             REAL,
    lon             REAL,
    download_link   TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_mid  ON memories(mid);
CREATE INDEX IF NOT EXISTS idx_memories_date ON memories(date_dt);

-- ── STORIES: Entries from shared_story.json ───────────────────────────────────
CREATE TABLE IF NOT EXISTS stories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id        TEXT,
    created         TEXT,
    created_dt      TEXT,
    content_type    TEXT
);

CREATE INDEX IF NOT EXISTS idx_stories_id   ON stories(story_id);
CREATE INDEX IF NOT EXISTS idx_stories_type ON stories(content_type);

-- ── SNAP_PRO: Saved stories from snap_pro.json ────────────────────────────────
CREATE TABLE IF NOT EXISTS snap_pro (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT,
    created         TEXT,
    created_dt      TEXT,
    title           TEXT
);

-- ── FRIENDS: Username to display name mapping ─────────────────────────────────
CREATE TABLE IF NOT EXISTS friends (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    category        TEXT
);

CREATE INDEX IF NOT EXISTS idx_friends_username ON friends(username);

-- ── LOCATIONS: GPS breadcrumbs from location_history.json ─────────────────────
CREATE TABLE IF NOT EXISTS locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    timestamp_unix  REAL NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    accuracy_m      REAL
);

CREATE INDEX IF NOT EXISTS idx_locations_ts ON locations(timestamp_unix);

-- ── PLACES: Snap Map places from snap_map_places.json ────────────────────────
CREATE TABLE IF NOT EXISTS places (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    lat             REAL,
    lon             REAL,
    address         TEXT,
    visit_count     INTEGER
);

-- ── MATCHES: Join table linking assets to metadata sources (Phase 2) ──────────
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES assets(id),
    strategy        TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.0,
    is_best         BOOLEAN NOT NULL DEFAULT 0,
    memory_id       INTEGER REFERENCES memories(id),
    chat_message_id INTEGER REFERENCES chat_messages(id),
    snap_message_id INTEGER REFERENCES snap_messages(id),
    story_id        INTEGER REFERENCES stories(id),
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

CREATE INDEX IF NOT EXISTS idx_matches_asset        ON matches(asset_id);
CREATE INDEX IF NOT EXISTS idx_matches_best         ON matches(asset_id, is_best);
CREATE INDEX IF NOT EXISTS idx_matches_strategy     ON matches(strategy);
CREATE INDEX IF NOT EXISTS idx_matches_lane         ON matches(lane);
CREATE INDEX IF NOT EXISTS idx_matches_chat_message ON matches(chat_message_id);
CREATE INDEX IF NOT EXISTS idx_matches_snap_message ON matches(snap_message_id);

-- ── RUN_LOG: Audit trail for each execution ───────────────────────────────────
CREATE TABLE IF NOT EXISTS run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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

-- ── REPROCESS_LOG: Audit trail for reprocessing runs (v3 addition) ────────────
CREATE TABLE IF NOT EXISTS reprocess_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    phases          TEXT,
    lanes           TEXT,
    triggered_by    TEXT,
    status          TEXT DEFAULT 'pending',
    result_json     TEXT
);

-- ── LANE_CONFIG: Per-lane user overrides (v3 addition) ───────────────────────
CREATE TABLE IF NOT EXISTS lane_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lane_name       TEXT UNIQUE NOT NULL,
    config_json     TEXT
);
