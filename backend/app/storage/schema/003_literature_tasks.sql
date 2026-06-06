-- Literature background tasks (multi-worker safe metadata + event log)

CREATE TABLE IF NOT EXISTS literature_tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    message TEXT NOT NULL,
    fetch_urls_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT 'starting',
    error TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    worker_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_literature_tasks_status_updated
    ON literature_tasks (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS literature_task_events (
    task_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_line TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (task_id, seq),
    FOREIGN KEY (task_id) REFERENCES literature_tasks (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_literature_task_events_task_seq
    ON literature_task_events (task_id, seq);
