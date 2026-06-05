"use client";

import { useEffect, useState } from "react";
import { Spin } from "antd";
import { toastError, toastSuccess, toastWarning } from "@/lib/toastFeedback";
import { feedbackOk, InlineField, SettingToolbar } from "../_ui";
import {
  entityFromTestError,
  errorMessage,
  formatVerifiedHint,
  isLlmCredential,
  mergeById,
  SettingsErrorMsg,
  SettingsLoading,
} from "../../_shared";
import { settingsApiV2, type SystemCapability, type SystemCredential } from "@/lib/settingsApiV2";
import { WebProviderTestPanel } from "./WebProviderTestPanel";

function mergeCredentialList(items: SystemCredential[], updated: SystemCredential): SystemCredential[] {
  return mergeById(items, updated);
}

function credentialFromTestError(e: unknown): SystemCredential | null {
  return entityFromTestError<SystemCredential>(e, "credential");
}

function CredentialRow({
  credential,
  onUpdated,
}: {
  credential: SystemCredential;
  onUpdated: (c: SystemCredential) => void;
}) {
  const [keyDraft, setKeyDraft] = useState<string | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [groupId, setGroupId] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [rowMsg, setRowMsg] = useState("");
  const [statusHint, setStatusHint] = useState("");

  const showLlmFields = isLlmCredential(credential);
  const keyEditing = keyDraft !== null;
  const inputValue =
    keyDraft !== null ? keyDraft : credential.has_secret ? credential.masked_secret : "";
  const inputType = keyEditing || !credential.has_secret ? "password" : "text";

  useEffect(() => {
    setKeyDraft(null);
    setBaseUrl(String(credential.base_url || ""));
    setGroupId(String(credential.group_id || ""));
    setRowMsg("");
    setStatusHint("");
  }, [credential.id, credential.base_url, credential.group_id]);

  useEffect(() => {
    setStatusHint(formatVerifiedHint(credential.last_verified_at));
  }, [credential.last_verified_at, credential.status]);

  const llmDirty =
    showLlmFields &&
    (baseUrl !== String(credential.base_url || "") || groupId !== String(credential.group_id || ""));
  const dirty = keyEditing || llmDirty;

  const onSave = async () => {
    setSaving(true);
    setRowMsg("");
    try {
      const body: { secret?: string; base_url?: string; group_id?: string } = {};
      if (keyEditing) body.secret = keyDraft ?? "";
      if (showLlmFields) {
        body.base_url = baseUrl.trim();
        body.group_id = groupId.trim();
      }
      const saved = await settingsApiV2.updateCredential(credential.id, body);
      onUpdated(saved);
      setKeyDraft(null);
      toastSuccess("已保存");
    } catch (e: unknown) {
      toastError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const onTest = async () => {
    if (!credential.has_secret && !keyEditing) {
      toastWarning("请先填写并保存 Key");
      return;
    }
    if (keyEditing) {
      toastWarning("请先保存 Key");
      return;
    }
    setTesting(true);
    setRowMsg("");
    try {
      const res = await settingsApiV2.testCredential(credential.id);
      const hits = typeof res.hits === "number" ? res.hits : null;
      const latest = res.credential || { ...credential, status: "ok" as const };
      onUpdated(latest);
      setStatusHint(
        hits !== null
          ? `连接测试已通过，命中 ${hits} 条`
          : "连接测试已通过",
      );
      toastSuccess(
        hits !== null ? `连接测试已通过，命中 ${hits} 条` : "连接测试已通过",
      );
    } catch (e: unknown) {
      const failed = credentialFromTestError(e);
      if (failed) {
        onUpdated(failed);
        const errText = e instanceof Error ? e.message : String(e);
        setStatusHint(errText);
        toastError(errText);
      } else {
        toastError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="card settings-cred-row">
      <SettingToolbar
        title={credential.name}
        status={credential.status}
        statusHint={statusHint || undefined}
        feedback={rowMsg}
        feedbackOk={rowMsg === "已保存"}
        actions={
          <>
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={(!credential.has_secret && !keyEditing) || testing || keyEditing}
              onClick={() => void onTest()}
            >
              {testing ? <Spin size="small" /> : null}
              测试
            </button>
            <button
              type="button"
              className="btn-primary btn-sm"
              disabled={saving || !dirty}
              onClick={() => void onSave()}
            >
              {saving ? <Spin size="small" /> : null}
              保存
            </button>
          </>
        }
      />

      <InlineField label="API Key" htmlFor={`cred-key-${credential.id}`}>
        <input
          id={`cred-key-${credential.id}`}
          className="input font-mono settings-inline-field__control"
          type={inputType}
          autoComplete="off"
          placeholder={credential.has_secret ? "点击输入新 Key" : "填写 Key"}
          value={inputValue}
          readOnly={!keyEditing && credential.has_secret}
          onFocus={() => {
            if (!keyEditing && credential.has_secret) setKeyDraft("");
          }}
          onBlur={() => {
            if (keyDraft === "") setKeyDraft(null);
          }}
          onChange={(e) => setKeyDraft(e.target.value)}
        />
      </InlineField>

      {showLlmFields ? (
        <div className="settings-cred-row__llm">
          <InlineField label="Base URL" htmlFor={`cred-url-${credential.id}`}>
            <input
              id={`cred-url-${credential.id}`}
              className="input font-mono settings-inline-field__control"
              placeholder="LLM 接口地址"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </InlineField>
          <InlineField label="Group ID" htmlFor={`cred-gid-${credential.id}`}>
            <input
              id={`cred-gid-${credential.id}`}
              className="input font-mono settings-inline-field__control"
              placeholder="可选"
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
            />
          </InlineField>
        </div>
      ) : null}
    </div>
  );
}

export default function AdminCredentialsPage() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<SystemCredential[]>([]);
  const [caps, setCaps] = useState<SystemCapability[]>([]);
  const [msg, setMsg] = useState("");

  const load = async (opts?: { quiet?: boolean }) => {
    if (!opts?.quiet) setLoading(true);
    try {
      const [credRes, capRes] = await Promise.all([
        settingsApiV2.listCredentials(),
        settingsApiV2.getSystemCapabilities(),
      ]);
      setItems(credRes.items || []);
      setCaps(capRes.items || []);
    } catch (e: unknown) {
      setMsg(errorMessage(e));
    } finally {
      if (!opts?.quiet) setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  if (loading) {
    return <SettingsLoading />;
  }

  const webSearchCap = caps.find((c) => c.capability_id === "web_search");
  const webFetchCap = caps.find((c) => c.capability_id === "web_fetch");
  const searchProvider = String(webSearchCap?.params?.search_provider ?? "native");
  const fetchProvider = String(webFetchCap?.params?.fetch_provider ?? "native");
  const pdfExtractBackend = String(webFetchCap?.params?.pdf_extract_backend ?? "pypdf");
  const fetchTimeoutSec = Number(webFetchCap?.params?.fetch_timeout_sec ?? 45);

  return (
    <div className="card settings-section settings-section--compact">
      <SettingsErrorMsg msg={msg} />

      <div className="settings-cred-list">
        {items.map((c) => (
          <CredentialRow
            key={c.id}
            credential={c}
            onUpdated={(updated) => {
              setItems((prev) => mergeCredentialList(prev, updated));
            }}
          />
        ))}

        <WebProviderTestPanel
          fetchProvider={fetchProvider}
          pdfExtractBackend={pdfExtractBackend}
          fetchTimeoutSec={fetchTimeoutSec}
          searchProvider={searchProvider}
        />
      </div>
    </div>
  );
}
