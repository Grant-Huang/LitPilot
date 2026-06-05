"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import {
  formatCapabilityParams,
  resolveCapabilityRefLabel,
} from "@/lib/capabilityFormat";
import { settingsApiV2, type StorageSettings } from "@/lib/settingsApiV2";
import { InlineField } from "./_ui";
import { SettingsErrorMsg, SettingsLoading, errorMessage } from "../_shared";

type Overview = Awaited<ReturnType<typeof settingsApiV2.getSystemOverview>>;
type Capability = Awaited<ReturnType<typeof settingsApiV2.getSystemCapabilities>>["items"][number];
type Credential = Awaited<ReturnType<typeof settingsApiV2.listCredentials>>["items"][number];
type Instance = Awaited<ReturnType<typeof settingsApiV2.listInstances>>["items"][number];

function storageBackendLabel(backend: string): string {
  if (backend === "turso") return "Turso（云端 SQLite）";
  if (backend === "hybrid") return "Hybrid（Turso + 本地缓存）";
  return "本地文件";
}

function StoragePanel({
  storage,
  onSaved,
}: {
  storage: StorageSettings;
  onSaved: (next: StorageSettings) => void;
}) {
  const [url, setUrl] = useState(storage.database_url || "");
  const [tokenDraft, setTokenDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [rowMsg, setRowMsg] = useState("");

  useEffect(() => {
    setUrl(storage.database_url || "");
    setTokenDraft(null);
    setRowMsg("");
  }, [storage.database_url, storage.masked_auth_token]);

  const tokenValue =
    tokenDraft !== null
      ? tokenDraft
      : storage.has_auth_token
        ? storage.masked_auth_token
        : "";

  const dirty =
    url.trim() !== (storage.database_url || "").trim() ||
    tokenDraft !== null;

  const handleSave = useCallback(async () => {
    setSaving(true);
    setRowMsg("");
    try {
      const body: { database_url?: string; auth_token?: string } = {};
      if (url.trim() !== (storage.database_url || "").trim()) {
        body.database_url = url.trim();
      }
      if (tokenDraft !== null) {
        body.auth_token = tokenDraft;
      }
      const next = await settingsApiV2.saveSystemStorage(body);
      onSaved(next);
      setTokenDraft(null);
      setRowMsg("已保存");
    } catch (e: unknown) {
      setRowMsg(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }, [url, tokenDraft, storage.database_url, onSaved]);

  return (
    <div className="card settings-section settings-section--compact" style={{ marginBottom: 12 }}>
      <div className="settings-overview-row" style={{ marginBottom: 12 }}>
        <div className="settings-overview-row__label">
          <span className="settings-overview-row__name">持久化存储</span>
          <span
            className={clsx(
              "settings-cred-status",
              storage.turso_ready ? "settings-cred-status--ok" : "settings-cred-status--pending",
            )}
          >
            {storage.turso_ready ? "Turso 已就绪" : "待配置 Turso"}
          </span>
        </div>
        <div className="settings-overview-row__value">
          {storageBackendLabel(storage.backend)}
          {storage.tenant_id && storage.tenant_id !== "default"
            ? ` · 租户 ${storage.tenant_id}`
            : ""}
        </div>
      </div>

      <p className="label" style={{ margin: "0 0 10px", color: "var(--meso-text-muted, #666)" }}>
        冷启动依赖环境变量（Vercel Dashboard 或本地 <code>.env</code>，已 gitignore）：{" "}
        <code>LITPILOT_STORAGE_BACKEND</code>、<code>TURSO_DATABASE_URL</code>、
        <code>TURSO_AUTH_TOKEN</code>。下方可保存运行期覆盖（即时生效）；本地开发与 Vercel 使用相同键名。
      </p>

      <InlineField label="Turso Database URL" htmlFor="turso-url">
        <input
          id="turso-url"
          className="input"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="libsql://your-db.turso.io"
          spellCheck={false}
        />
      </InlineField>

      <InlineField label="Turso Auth Token" htmlFor="turso-token">
        <input
          id="turso-token"
          className="input"
          type="password"
          value={tokenValue}
          onChange={(e) => setTokenDraft(e.target.value)}
          onFocus={() => {
            if (tokenDraft === null) setTokenDraft("");
          }}
          placeholder={storage.has_auth_token ? "留空表示不修改" : "粘贴 Token"}
          spellCheck={false}
        />
      </InlineField>

      <div className="settings-inline-field" style={{ marginTop: 8 }}>
        <span className="label settings-inline-field__label">来源</span>
        <span className="settings-inline-field__control" style={{ fontSize: 13 }}>
          URL: {storage.database_url_source || "none"} · Token: {storage.auth_token_source || "none"}
          {storage.env_has_url ? " · env✓" : ""}
          {storage.admin_has_url ? " · admin✓" : ""}
        </span>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!dirty || saving}
          onClick={() => void handleSave()}
        >
          {saving ? "保存中…" : "保存存储配置"}
        </button>
        {rowMsg ? <span className="label">{rowMsg}</span> : null}
      </div>
    </div>
  );
}

export default function AdminSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [caps, setCaps] = useState<Capability[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [storage, setStorage] = useState<StorageSettings | null>(null);

  useEffect(() => {
    void Promise.all([
      settingsApiV2.getSystemOverview(),
      settingsApiV2.getSystemCapabilities().then((r) => r.items || []),
      settingsApiV2.listCredentials().then((r) => r.items || []),
      settingsApiV2.listInstances().then((r) => r.items || []),
    ])
      .then(([ov, c, cred, inst]) => {
        const overviewData = ov as Overview;
        setOverview(overviewData);
        setStorage(overviewData.storage);
        setCaps(c as Capability[]);
        setCredentials(cred as Credential[]);
        setInstances(inst as Instance[]);
      })
      .catch((e: unknown) => setMsg(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  const readiness = useMemo(() => {
    const caps = overview?.capabilities || [];
    const byId: Record<string, boolean> = {};
    for (const c of caps) byId[String(c.capability_id)] = Boolean(c.ok) && Boolean(c.enabled);
    return byId;
  }, [overview]);

  const summary = useMemo(() => {
    const credById = new Map(credentials.map((c) => [c.id, c]));
    const instById = new Map(instances.map((i) => [i.id, i]));
    const capById = new Map(caps.map((c) => [c.capability_id, c]));

    const row = (id: string, label: string) => {
      const cap = capById.get(id);
      const ref = resolveCapabilityRefLabel(cap, credById, instById);
      const params = formatCapabilityParams(id, cap?.params);
      const value = params ? `${ref} · ${params}` : ref;
      return { id, label, value };
    };

    return [
      row("review_main", "综述主模型"),
      row("orchestrator", "编排模型"),
      row("web_search", "Tavily"),
      row("web_fetch", "Jina"),
    ];
  }, [caps, credentials, instances]);

  if (loading) {
    return <SettingsLoading />;
  }

  return (
    <>
      {storage ? (
        <StoragePanel storage={storage} onSaved={setStorage} />
      ) : null}

      <div className="card settings-section settings-section--compact">
        <SettingsErrorMsg msg={msg} />

        <div className="settings-overview-list">
          {summary.map((row) => (
            <div key={row.id} className="settings-overview-row">
              <div className="settings-overview-row__label">
                <span className="settings-overview-row__name">{row.label}</span>
                <span
                  className={clsx(
                    "settings-cred-status",
                    readiness[row.id] ? "settings-cred-status--ok" : "settings-cred-status--pending",
                  )}
                >
                  {readiness[row.id] ? "已就绪" : "待配置"}
                </span>
              </div>
              <div className="settings-overview-row__value">{row.value}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
