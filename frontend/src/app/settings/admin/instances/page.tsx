"use client";

import { useEffect, useState } from "react";
import { Spin } from "antd";
import clsx from "clsx";
import { ApiError } from "@/lib/http";
import { feedbackOk, InlineField, SettingToolbar } from "../_ui";
import { settingsApiV2, type SystemCredential, type SystemInstance } from "@/lib/settingsApiV2";

function isLlmCredential(c: SystemCredential): boolean {
  return String(c.type || "").startsWith("llm:");
}

function mergeInstances(items: SystemInstance[], updated: SystemInstance): SystemInstance[] {
  return items.map((x) => (x.id === updated.id ? { ...x, ...updated } : x));
}

function InstanceRow({
  instance,
  credentials,
  onUpdated,
}: {
  instance: SystemInstance;
  credentials: SystemCredential[];
  onUpdated: (i: SystemInstance) => void;
}) {
  const llmCreds = credentials.filter(isLlmCredential);
  const [name, setName] = useState(instance.name || "");
  const [credentialId, setCredentialId] = useState(instance.credential_id || "");
  const [modelName, setModelName] = useState(instance.model_name || "");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [rowMsg, setRowMsg] = useState("");
  const [statusHint, setStatusHint] = useState("");

  useEffect(() => {
    setName(instance.name || "");
    setCredentialId(instance.credential_id || "");
    setModelName(instance.model_name || "");
    setRowMsg("");
    setStatusHint("");
  }, [instance.id]);

  useEffect(() => {
    setStatusHint(
      instance.last_verified_at
        ? `最近测试：${new Date(instance.last_verified_at).toLocaleString()}`
        : "",
    );
  }, [instance.last_verified_at, instance.status]);

  const dirty =
    name !== (instance.name || "") ||
    credentialId !== (instance.credential_id || "") ||
    modelName !== (instance.model_name || "");

  const onSave = async () => {
    setSaving(true);
    setRowMsg("");
    try {
      const saved = await settingsApiV2.updateInstance(instance.id, {
        name: name.trim() || instance.name,
        credential_id: credentialId,
        model_name: modelName.trim() || instance.model_name,
      });
      onUpdated(saved);
      setRowMsg("已保存");
    } catch (e: unknown) {
      setRowMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const onTest = async () => {
    if (dirty) {
      setRowMsg("请先保存");
      return;
    }
    setTesting(true);
    setRowMsg("");
    try {
      const res = await settingsApiV2.testInstance(instance.id);
      const updated = res.instance || { ...instance, status: "ok" as const };
      onUpdated(updated);
      setStatusHint(String(res.note || "已通过基础检查"));
    } catch (e: unknown) {
      const failed =
        e instanceof ApiError && e.data && typeof e.data === "object"
          ? (e.data as { instance?: SystemInstance }).instance
          : null;
      if (failed) {
        onUpdated(failed);
        setStatusHint(e instanceof Error ? e.message : String(e));
      } else {
        setRowMsg(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="card settings-cred-row">
      <SettingToolbar
        title={name.trim() || instance.name}
        status={instance.status}
        statusHint={statusHint || undefined}
        feedback={rowMsg}
        feedbackOk={rowMsg === "已保存"}
        actions={
          <>
            <button type="button" className="btn-secondary btn-sm" disabled={testing || dirty} onClick={() => void onTest()}>
              {testing ? <Spin size="small" /> : null}
              测试
            </button>
            <button type="button" className="btn-primary btn-sm" disabled={saving || !dirty} onClick={() => void onSave()}>
              {saving ? <Spin size="small" /> : null}
              保存
            </button>
          </>
        }
      />
      <div className="settings-inst-fields">
        <InlineField label="名称" htmlFor={`inst-name-${instance.id}`}>
          <input
            id={`inst-name-${instance.id}`}
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </InlineField>
        <InlineField label="凭据" htmlFor={`inst-cred-${instance.id}`}>
          <select
            id={`inst-cred-${instance.id}`}
            className="input settings-select"
            value={credentialId}
            onChange={(e) => setCredentialId(e.target.value)}
          >
            <option value="">选择 LLM 凭据…</option>
            {llmCreds.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.has_secret ? c.masked_secret : "未配置"}
              </option>
            ))}
          </select>
        </InlineField>
        <InlineField label="模型" htmlFor={`inst-model-${instance.id}`}>
          <input
            id={`inst-model-${instance.id}`}
            className="input font-mono"
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
          />
        </InlineField>
      </div>
    </div>
  );
}

function CreateInstancePanel({
  credentials,
  onCreated,
  onCancel,
}: {
  credentials: SystemCredential[];
  onCreated: (i: SystemInstance) => void;
  onCancel: () => void;
}) {
  const llmCreds = credentials.filter(isLlmCredential);
  const [name, setName] = useState("");
  const [credentialId, setCredentialId] = useState(llmCreds[0]?.id || "");
  const [modelName, setModelName] = useState("MiniMax-M3");
  const [saving, setSaving] = useState(false);
  const [rowMsg, setRowMsg] = useState("");

  const providerFromCredential = (id: string): string => {
    const c = credentials.find((x) => x.id === id);
    const t = String(c?.type || "");
    if (t.startsWith("llm:")) return t.slice("llm:".length);
    return "unknown";
  };

  const onCreate = async () => {
    if (!credentialId) {
      setRowMsg("请选择凭据");
      return;
    }
    setSaving(true);
    setRowMsg("");
    try {
      const created = await settingsApiV2.createInstance({
        name: name.trim() || "new-instance",
        provider: providerFromCredential(credentialId),
        credential_id: credentialId,
        model_name: modelName.trim() || "MiniMax-M3",
        default_params: {},
      });
      onCreated(created);
    } catch (e: unknown) {
      setRowMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card settings-cred-row settings-inst-create">
      <SettingToolbar
        title="新增实例"
        feedback={rowMsg}
        feedbackOk={feedbackOk(rowMsg)}
        actions={
          <>
            <button type="button" className="btn-secondary btn-sm" onClick={onCancel}>
              取消
            </button>
            <button type="button" className="btn-primary btn-sm" disabled={saving} onClick={() => void onCreate()}>
              {saving ? <Spin size="small" /> : null}
              创建
            </button>
          </>
        }
      />
      <div className="settings-inst-fields">
        <InlineField label="名称" htmlFor="inst-new-name">
          <input
            id="inst-new-name"
            className="input"
            placeholder="review-main"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </InlineField>
        <InlineField label="凭据" htmlFor="inst-new-cred">
          <select
            id="inst-new-cred"
            className="input settings-select"
            value={credentialId}
            onChange={(e) => setCredentialId(e.target.value)}
          >
            {llmCreds.length ? null : <option value="">无可用 LLM 凭据</option>}
            {llmCreds.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.has_secret ? c.masked_secret : "未配置"}
              </option>
            ))}
          </select>
        </InlineField>
        <InlineField label="模型" htmlFor="inst-new-model">
          <input
            id="inst-new-model"
            className="input font-mono"
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
          />
        </InlineField>
      </div>
    </div>
  );
}

export default function AdminInstancesPage() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<SystemInstance[]>([]);
  const [credentials, setCredentials] = useState<SystemCredential[]>([]);
  const [msg, setMsg] = useState("");
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    setMsg("");
    try {
      const [instRes, credRes] = await Promise.all([settingsApiV2.listInstances(), settingsApiV2.listCredentials()]);
      setItems(instRes.items || []);
      setCredentials(credRes.items || []);
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  if (loading) {
    return (
      <div className="settings-admin-loading">
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="card settings-section settings-section--compact">
      <div className="settings-page-toolbar">
        <button type="button" className="btn-primary btn-sm" onClick={() => setCreating((v) => !v)}>
          {creating ? "收起" : "新增实例"}
        </button>
      </div>

      {msg ? <div className={clsx("settings-msg", "settings-msg--err")}>{msg}</div> : null}

      <div className="settings-cred-list">
        {creating ? (
          <CreateInstancePanel
            credentials={credentials}
            onCancel={() => setCreating(false)}
            onCreated={(created) => {
              setItems((prev) => [created, ...prev]);
              setCreating(false);
            }}
          />
        ) : null}
        {items.map((i) => (
          <InstanceRow
            key={i.id}
            instance={i}
            credentials={credentials}
            onUpdated={(updated) => setItems((prev) => mergeInstances(prev, updated))}
          />
        ))}
      </div>
    </div>
  );
}
