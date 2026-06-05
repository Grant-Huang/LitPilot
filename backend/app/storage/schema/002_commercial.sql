-- P5: multi-tenant scaffolding (single-tenant default)
ALTER TABLE sessions ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE library_items ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_sessions_tenant_updated
    ON sessions (tenant_id, pinned DESC, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_library_items_tenant_display
    ON library_items (tenant_id, display_index);
