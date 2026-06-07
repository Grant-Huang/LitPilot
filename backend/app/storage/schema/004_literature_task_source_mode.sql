-- Persist per-task literature source mode (merge / user_only)

ALTER TABLE literature_tasks ADD COLUMN literature_source_mode TEXT;
