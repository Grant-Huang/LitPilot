-- LitPilot Turso core schema (P0–P3)
-- Apply via: python scripts/turso_setup.py

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Sessions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '新综述',
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_pinned_updated ON sessions (pinned DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta_json TEXT,
    ts TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_session_messages_session_seq
    ON session_messages (session_id, seq);

CREATE TABLE IF NOT EXISTS session_documents (
    session_id TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    content_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (session_id, doc_type),
    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    is_latest INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_artifacts_latest
    ON session_artifacts (session_id, kind, is_latest);

-- ---------------------------------------------------------------------------
-- Settings v2 (JSON documents)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS config_documents (
    doc_key TEXT PRIMARY KEY,
    content_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Library
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL DEFAULT 1,
    next_display_index INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO library_meta (id, version, next_display_index, updated_at)
VALUES (1, 1, 0, datetime('now'));

CREATE TABLE IF NOT EXISTS library_items (
    id TEXT PRIMARY KEY,
    canonical_key TEXT UNIQUE,
    display_index INTEGER NOT NULL,
    item_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_library_items_display ON library_items (display_index);

-- ---------------------------------------------------------------------------
-- Blob registry (P4: PDF / sources, content optional inline)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS blob_files (
    path TEXT PRIMARY KEY,
    storage TEXT NOT NULL DEFAULT 'local',
    content_blob BLOB,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
