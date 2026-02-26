-- Migration: 001_upload_sessions.sql
-- Date: 2026-02-24
-- Purpose: Add upload_sessions and upload_files tables for chunked multi-file upload system

-- Upload sessions (one per upload attempt)
CREATE TABLE IF NOT EXISTS upload_sessions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id),
    session_token   TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL DEFAULT 'active',
    file_count      INT NOT NULL,
    total_bytes     BIGINT NOT NULL,
    bytes_received  BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    job_id          BIGINT REFERENCES processing_jobs(id)
);

-- Individual files within a session
CREATE TABLE IF NOT EXISTS upload_files (
    id              BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES upload_sessions(id) ON DELETE CASCADE,
    file_index      INT NOT NULL,
    filename        TEXT NOT NULL,
    file_size       BIGINT NOT NULL,
    sha256_expected TEXT NOT NULL,
    sha256_actual   TEXT,
    bytes_received  BIGINT NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    completed_at    TIMESTAMPTZ,
    UNIQUE(session_id, file_index)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_upload_sessions_user ON upload_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_upload_sessions_token ON upload_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_upload_sessions_expires ON upload_sessions(expires_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_upload_files_session ON upload_files(session_id);
