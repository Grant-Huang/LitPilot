"use client";

import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { settingsApiV2, type StorageSettings } from "@/lib/settingsApiV2";
import { feedbackOk, InlineField, SettingToolbar, useUnsavedGuard } from "./_ui";
import { errorMessage } from "../_shared";

const STORAGE_DEPLOY_TIP =
  "冷启动依赖环境变量（Vercel Dashboard 或本地 .env，已 gitignore）：LITPILOT_STORAGE_BACKEND、TURSO_DATABASE_URL、TURSO_AUTH_TOKEN。下方可保存运行期覆盖（即时生效）。";

export function storageBackendLabel(backend: string): string {
  if (backend === "turso") return "Turso（云端 SQLite）";
  if (backend === "hybrid") return "Hybrid（Turso + 本地缓存）";
  return "本地文件";
}

function formatSourceLabel(source: string | undefined): string {
  const s = String(source || "none").toLowerCase();
  if (s === "env") return "环境变量";
  if (s === "admin") return "管理员配置";
  if (s === "none") return "未配置";
  return source || "未知";
}

export function StorageSettingsPanel({
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
    tokenDraft !== null ? tokenDraft : storage.has_auth_token ? storage.masked_auth_token : "";

  const dirty = url.trim() !== (storage.database_url || "").trim() || tokenDraft !== null;

  useUnsavedGuard(dirty);

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

  const statusLabel = storage.turso_ready ? "已通过" : "待配置";
  const statusValue = storage.turso_ready ? "ok" : "pending";

  return (
    <div className="settings-cred-row settings-list-row">
      <SettingToolbar
        title="持久化存储"
        status={statusValue}
        statusHint={
          storage.turso_ready
            ? `${storageBackendLabel(storage.backend)} · 连接正常`
            : "请配置 Turso Database URL 与 Auth Token"
        }
        extra={
          <span className="settings-storage-meta">
            {storageBackendLabel(storage.backend)}
            {storage.tenant_id && storage.tenant_id !== "default"
              ? ` · 租户 ${storage.tenant_id}`
              : ""}
          </span>
        }
        feedback={rowMsg}
        feedbackOk={feedbackOk(rowMsg)}
        actions={
          <button
            type="button"
            className="btn-primary btn-sm"
            disabled={!dirty || saving}
            onClick={() => void handleSave()}
          >
            {saving ? "保存中…" : "保存"}
          </button>
        }
      />

      <details className="settings-advanced settings-storage-deploy">
        <summary className="settings-advanced__summary">部署说明</summary>
        <div className="settings-advanced__body">
          <p className="settings-field-note">{STORAGE_DEPLOY_TIP}</p>
        </div>
      </details>

      <InlineField label="数据库 URL" htmlFor="turso-url" tip="Turso libsql 连接地址，如 libsql://your-db.turso.io">
        <input
          id="turso-url"
          className="input font-mono"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="libsql://your-db.turso.io"
          spellCheck={false}
        />
      </InlineField>

      <InlineField label="Auth Token" htmlFor="turso-token" tip="Turso 数据库访问令牌；留空表示不修改已保存的 Token">
        <input
          id="turso-token"
          className="input font-mono"
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

      <InlineField label="配置来源">
        <span className="settings-storage-sources">
          <span
            className={clsx(
              "settings-cred-status",
              storage.env_has_url ? "settings-cred-status--ok" : "settings-cred-status--pending",
            )}
            title="Database URL 是否来自环境变量"
          >
            URL · {formatSourceLabel(storage.database_url_source)}
          </span>
          <span
            className={clsx(
              "settings-cred-status",
              storage.env_has_url && storage.auth_token_source === "env"
                ? "settings-cred-status--ok"
                : storage.has_auth_token
                  ? "settings-cred-status--ok"
                  : "settings-cred-status--pending",
            )}
            title="Auth Token 是否来自环境变量或管理员配置"
          >
            Token · {formatSourceLabel(storage.auth_token_source)}
          </span>
        </span>
      </InlineField>
    </div>
  );
}
