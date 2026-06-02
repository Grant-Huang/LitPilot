"use client";

import { useEffect, useMemo, useState } from "react";
import { Spin } from "antd";
import clsx from "clsx";
import { feedbackOk, InlineField, SettingToolbar } from "../_ui";
import {
  settingsApiV2,
  type SystemCapability,
  type SystemCredential,
  type SystemInstance,
} from "@/lib/settingsApiV2";

function CapabilityCard({
  cap,
  credentials,
  instances,
  onSaved,
}: {
  cap: SystemCapability;
  credentials: SystemCredential[];
  instances: SystemInstance[];
  onSaved: (cap: SystemCapability) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [enabled, setEnabled] = useState(Boolean(cap.enabled));
  const [refId, setRefId] = useState(String(cap.primary_ref?.id || ""));
  const [params, setParams] = useState<Record<string, unknown>>({ ...(cap.params || {}) });

  useEffect(() => {
    setEnabled(Boolean(cap.enabled));
    setRefId(String(cap.primary_ref?.id || ""));
    setParams({ ...(cap.params || {}) });
    setMsg("");
    setSaving(false);
  }, [cap]);

  const refOptions = useMemo(() => {
    if (cap.capability_id === "review_main" || cap.capability_id === "orchestrator") {
      return {
        kind: "instance",
        items: instances.map((i) => ({ id: i.id, label: `${i.name} · ${i.provider} · ${i.model_name}` })),
      };
    }
    if (cap.capability_id === "web_search" || cap.capability_id === "web_fetch") {
      const typePrefix = cap.capability_id === "web_search" ? "tavily" : "jina";
      return {
        kind: "credential",
        items: credentials
          .filter((c) => String(c.type || "").startsWith(typePrefix))
          .map((c) => ({ id: c.id, label: `${c.name} · ${c.has_secret ? c.masked_secret : "未配置"}` })),
      };
    }
    return { kind: "", items: [] as Array<{ id: string; label: string }> };
  }, [cap.capability_id, credentials, instances]);

  const refLabel =
    refOptions.kind === "instance"
      ? "实例"
      : cap.capability_id === "web_search"
        ? "Tavily"
        : cap.capability_id === "web_fetch"
          ? "Jina"
          : "绑定";

  const refPlaceholder =
    refOptions.kind === "instance" ? "选择模型实例…" : `选择${refLabel}凭据…`;

  const needsRef =
    cap.capability_id === "review_main" ||
    cap.capability_id === "orchestrator" ||
    cap.capability_id === "web_search" ||
    cap.capability_id === "web_fetch";

  const save = async () => {
    setSaving(true);
    setMsg("");
    try {
      const primary_ref =
        refOptions.kind && refId
          ? ({ kind: refOptions.kind, id: refId } as Record<string, unknown>)
          : null;
      const saved = await settingsApiV2.updateCapability(cap.capability_id, {
        enabled,
        primary_ref,
        params,
      });
      onSaved(saved);
      setMsg("已保存");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const renderParams = () => {
    const domainsToText = (v: unknown): string => {
      if (Array.isArray(v)) return v.map(String).join("\n");
      if (typeof v === "string") return v;
      return "";
    };
    const parseDomains = (text: string): string[] =>
      text
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter(Boolean);

    if (cap.capability_id === "web_search") {
      return (
        <>
          <div className="settings-cap-params-grid">
            <InlineField label="检索条数" htmlFor={`${cap.capability_id}-max`}>
              <input
                id={`${cap.capability_id}-max`}
                className="input"
                type="number"
                min={1}
                max={80}
                value={Number(params.tavily_max_results ?? 8)}
                onChange={(e) => setParams((p) => ({ ...p, tavily_max_results: Number(e.target.value) }))}
              />
            </InlineField>
            <InlineField label="失败重试" htmlFor={`${cap.capability_id}-retry`}>
              <input
                id={`${cap.capability_id}-retry`}
                className="input"
                type="number"
                min={0}
                max={3}
                value={Number(params.tavily_retry_count ?? 0)}
                onChange={(e) => setParams((p) => ({ ...p, tavily_retry_count: Number(e.target.value) }))}
              />
            </InlineField>
            <InlineField label="检索深度" htmlFor={`${cap.capability_id}-depth`}>
              <select
                id={`${cap.capability_id}-depth`}
                className="input settings-select"
                value={String(params.search_depth ?? "advanced")}
                onChange={(e) => setParams((p) => ({ ...p, search_depth: e.target.value }))}
              >
                <option value="basic">basic</option>
                <option value="advanced">advanced</option>
              </select>
            </InlineField>
          </div>
          <InlineField label="包含域名" htmlFor={`${cap.capability_id}-inc`}>
            <textarea
              id={`${cap.capability_id}-inc`}
              className="input settings-textarea-compact"
              rows={4}
              placeholder="每行一个域名，如 arxiv.org"
              value={domainsToText(params.include_domains)}
              onChange={(e) => setParams((p) => ({ ...p, include_domains: parseDomains(e.target.value) }))}
            />
          </InlineField>
          <InlineField label="排除域名" htmlFor={`${cap.capability_id}-exc`}>
            <textarea
              id={`${cap.capability_id}-exc`}
              className="input settings-textarea-compact"
              rows={3}
              placeholder="每行一个域名"
              value={domainsToText(params.exclude_domains)}
              onChange={(e) => setParams((p) => ({ ...p, exclude_domains: parseDomains(e.target.value) }))}
            />
          </InlineField>
          <label className="settings-cap-inline-check">
            <input
              type="checkbox"
              checked={Boolean(params.enforce_domain_filter ?? true)}
              onChange={(e) => setParams((p) => ({ ...p, enforce_domain_filter: e.target.checked }))}
            />
            强制域名白名单过滤
          </label>
          <label className="settings-cap-inline-check">
            <input
              type="checkbox"
              checked={Boolean(params.enable_junk_filter ?? true)}
              onChange={(e) => setParams((p) => ({ ...p, enable_junk_filter: e.target.checked }))}
            />
            启用 junk 过滤
          </label>
          <label className="settings-cap-inline-check">
            <input
              type="checkbox"
              checked={Boolean(params.enable_query_expansion ?? false)}
              onChange={(e) => setParams((p) => ({ ...p, enable_query_expansion: e.target.checked }))}
            />
            启用检索扩展（多 query 合并）
          </label>
          <InlineField label="扩展条数" htmlFor={`${cap.capability_id}-exp`}>
            <input
              id={`${cap.capability_id}-exp`}
              className="input"
              type="number"
              min={1}
              max={4}
              value={Number(params.expansion_count ?? 3)}
              onChange={(e) => setParams((p) => ({ ...p, expansion_count: Number(e.target.value) }))}
            />
          </InlineField>
        </>
      );
    }
    if (cap.capability_id === "web_fetch") {
      return (
        <div className="settings-cap-params-grid">
          <InlineField label="抓取篇数" htmlFor={`${cap.capability_id}-urls`}>
            <input
              id={`${cap.capability_id}-urls`}
              className="input"
              type="number"
              min={1}
              max={50}
              value={Number(params.max_fetch_urls ?? 5)}
              onChange={(e) => setParams((p) => ({ ...p, max_fetch_urls: Number(e.target.value) }))}
            />
          </InlineField>
          <InlineField label="并行" htmlFor={`${cap.capability_id}-par`}>
            <input
              id={`${cap.capability_id}-par`}
              className="input"
              type="number"
              min={1}
              max={8}
              value={Number(params.fetch_parallel ?? 3)}
              onChange={(e) => setParams((p) => ({ ...p, fetch_parallel: Number(e.target.value) }))}
            />
          </InlineField>
          <InlineField label="超时(秒)" htmlFor={`${cap.capability_id}-to`}>
            <input
              id={`${cap.capability_id}-to`}
              className="input"
              type="number"
              min={10}
              max={120}
              value={Number(params.fetch_timeout_sec ?? 45)}
              onChange={(e) => setParams((p) => ({ ...p, fetch_timeout_sec: Number(e.target.value) }))}
            />
          </InlineField>
          <InlineField label="重试" htmlFor={`${cap.capability_id}-rc`}>
            <input
              id={`${cap.capability_id}-rc`}
              className="input"
              type="number"
              min={0}
              max={3}
              value={Number(params.fetch_retry_count ?? 0)}
              onChange={(e) => setParams((p) => ({ ...p, fetch_retry_count: Number(e.target.value) }))}
            />
          </InlineField>
          <InlineField label="单篇上限(字)" htmlFor={`${cap.capability_id}-chars`}>
            <input
              id={`${cap.capability_id}-chars`}
              className="input"
              type="number"
              min={2000}
              max={50000}
              value={Number(params.max_source_chars ?? 14000)}
              onChange={(e) => setParams((p) => ({ ...p, max_source_chars: Number(e.target.value) }))}
            />
          </InlineField>
        </div>
      );
    }
    if (cap.capability_id === "orchestrator") {
      return (
        <>
          <label className="settings-cap-inline-check">
            <input
              type="checkbox"
              checked={Boolean(params.use_llm_planner ?? true)}
              onChange={(e) => setParams((p) => ({ ...p, use_llm_planner: e.target.checked }))}
            />
            LLM 规划与解说
          </label>
          <label className="settings-cap-inline-check">
            <input
              type="checkbox"
              checked={Boolean(params.orchestrator_use_reasoning ?? false)}
              onChange={(e) => setParams((p) => ({ ...p, orchestrator_use_reasoning: e.target.checked }))}
            />
            启用 reasoning 模式
          </label>
          <div className="settings-cap-params-grid">
            <InlineField label="解说密度" htmlFor={`${cap.capability_id}-mode`}>
              <select
                id={`${cap.capability_id}-mode`}
                className="input settings-select"
                value={String(params.orchestrator_mode ?? "lite")}
                onChange={(e) => setParams((p) => ({ ...p, orchestrator_mode: e.target.value }))}
              >
                <option value="off">off</option>
                <option value="lite">lite</option>
                <option value="full">full</option>
              </select>
            </InlineField>
            <InlineField label="Token/阶段" htmlFor={`${cap.capability_id}-tok`}>
              <input
                id={`${cap.capability_id}-tok`}
                className="input"
                type="number"
                min={80}
                max={500}
                value={Number(params.orchestrator_max_tokens_per_phase ?? 280)}
                onChange={(e) =>
                  setParams((p) => ({ ...p, orchestrator_max_tokens_per_phase: Number(e.target.value) }))
                }
              />
            </InlineField>
          </div>
        </>
      );
    }
    if (cap.capability_id === "literature_source") {
      return (
        <InlineField label="来源策略" htmlFor={`${cap.capability_id}-src`}>
          <select
            id={`${cap.capability_id}-src`}
            className="input settings-select"
            value={String(params.literature_source_mode ?? "merge")}
            onChange={(e) => setParams((p) => ({ ...p, literature_source_mode: e.target.value }))}
          >
            <option value="merge">合并（用户链接 + Tavily）</option>
            <option value="user_only">仅用户列表</option>
          </select>
        </InlineField>
      );
    }
    return null;
  };

  const paramsEl = renderParams();

  return (
    <div className="card settings-cred-row">
      <SettingToolbar
        title={cap.label || cap.capability_id}
        titleMuted={!enabled}
        feedback={msg}
        feedbackOk={feedbackOk(msg)}
        extra={
          <label className="settings-cap-enable">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            启用
          </label>
        }
        actions={
          <button type="button" className="btn-primary btn-sm" onClick={() => void save()} disabled={saving}>
            {saving ? <Spin size="small" /> : null}
            保存
          </button>
        }
      />

      {needsRef ? (
        <InlineField label={refLabel} htmlFor={`${cap.capability_id}-ref`}>
          <select
            id={`${cap.capability_id}-ref`}
            className="input settings-select"
            value={refId}
            onChange={(e) => setRefId(e.target.value)}
          >
            <option value="">{refPlaceholder}</option>
            {refOptions.items.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </InlineField>
      ) : null}

      {paramsEl ? <div className="settings-cap-card__params">{paramsEl}</div> : null}
    </div>
  );
}

export default function AdminCapabilitiesPage() {
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [caps, setCaps] = useState<SystemCapability[]>([]);
  const [credentials, setCredentials] = useState<SystemCredential[]>([]);
  const [instances, setInstances] = useState<SystemInstance[]>([]);

  useEffect(() => {
    void Promise.all([
      settingsApiV2.getSystemCapabilities(),
      settingsApiV2.listCredentials(),
      settingsApiV2.listInstances(),
    ])
      .then(([capRes, credRes, instRes]) => {
        setCaps(capRes.items || []);
        setCredentials(credRes.items || []);
        setInstances(instRes.items || []);
      })
      .catch((e: unknown) => setMsg(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
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
      {msg ? <div className={clsx("settings-msg", "settings-msg--err")}>{msg}</div> : null}

      <div className="settings-cap-list">
        {caps
          .filter((c) => c.capability_id !== "prompts")
          .map((c) => (
            <CapabilityCard
              key={c.capability_id}
              cap={c}
              credentials={credentials}
              instances={instances}
              onSaved={(saved) => {
                setCaps((prev) => prev.map((x) => (x.capability_id === saved.capability_id ? saved : x)));
              }}
            />
          ))}
      </div>
    </div>
  );
}
