"use client";

import { useEffect, useMemo, useState } from "react";
import { Spin } from "antd";
import { FieldTip, InlineCheck, InlineField, SettingToolbar, SettingsListPanel, feedbackOk, useUnsavedGuard } from "../_ui";
import {
  capabilityDisplayTitle,
  capabilityNeedsCredentialRef,
  capabilityRefLabel,
  capabilityRefOptions,
} from "@/lib/capabilityFormat";
import {
  CAP_TIPS,
  capabilityModuleTip,
  SEARCH_FETCH_CAPABILITY_IDS,
  sortCapabilities,
} from "@/lib/capabilityTips";
import {
  fetchProviderNeedsCredential,
  fetchProviderOptions,
  searchProviderNeedsCredential,
  searchProviderOptions,
} from "@/lib/webProviderOptions";
import { loadAdminBootstrap, invalidateAdminBootstrap } from "@/lib/settingsBootstrap";
import { SettingsErrorMsg, SettingsListSkeleton, errorMessage } from "../../_shared";
import { toastError } from "@/lib/toastFeedback";
import {
  settingsApiV2,
  type SystemCapability,
  type SystemCredential,
  type SystemInstance,
} from "@/lib/settingsApiV2";

function paramsEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

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
  const [rowMsg, setRowMsg] = useState("");
  const [refId, setRefId] = useState(String(cap.primary_ref?.id || ""));
  const [params, setParams] = useState<Record<string, unknown>>({ ...(cap.params || {}) });

  useEffect(() => {
    setRefId(String(cap.primary_ref?.id || ""));
    setParams({ ...(cap.params || {}) });
    setSaving(false);
    setRowMsg("");
  }, [cap]);

  const refOptions = useMemo(
    () => capabilityRefOptions({ ...cap, params }, credentials, instances),
    [cap, credentials, instances, params],
  );

  const needsRef = capabilityNeedsCredentialRef(cap, params);

  const refLabel =
    refOptions.kind === "instance"
      ? "实例"
      : capabilityRefLabel(cap.capability_id, params);

  const refPlaceholder =
    refOptions.kind === "instance" ? "选择模型实例…" : `选择${refLabel}…`;

  const instanceTip =
    cap.capability_id === "orchestrator"
      ? CAP_TIPS.orchestrator_instance
      : cap.capability_id === "review_main"
        ? CAP_TIPS.review_instance
        : undefined;

  const dirty =
    refId !== String(cap.primary_ref?.id || "") ||
    !paramsEqual(params, { ...(cap.params || {}) });

  useUnsavedGuard(dirty);

  const save = async () => {
    setSaving(true);
    setRowMsg("");
    try {
      const needsCred = capabilityNeedsCredentialRef(cap, params);
      const primary_ref =
        refOptions.kind && refId && needsCred
          ? ({ kind: refOptions.kind, id: refId } as Record<string, unknown>)
          : null;
      const saved = await settingsApiV2.updateCapability(cap.capability_id, {
        primary_ref,
        params,
      });
      invalidateAdminBootstrap();
      onSaved(saved);
      setRowMsg("已保存");
    } catch (e: unknown) {
      setRowMsg(errorMessage(e));
      toastError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const renderParams = () => {
    const searchProviders = searchProviderOptions(credentials);
    const fetchProviders = fetchProviderOptions(credentials);
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
      const searchProvider = String(params.search_provider ?? "multi_academic");
      const isApiSearch = searchProviderNeedsCredential(searchProvider);
      const searchDepthTip = `${CAP_TIPS.search_depth_basic}\n${CAP_TIPS.search_depth_advanced}`;
      return (
        <>
          <InlineField
            label="检索后端"
            htmlFor={`${cap.capability_id}-provider`}
            tip={CAP_TIPS.search_provider}
          >
            <select
              id={`${cap.capability_id}-provider`}
              className="input settings-select"
              value={searchProvider}
              onChange={(e) =>
                setParams((p) => ({
                  ...p,
                  search_provider: e.target.value,
                }))
              }
            >
              {searchProviders.map((opt) => (
                <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                  {opt.label}
                  {opt.disabled ? "（未配置 Key）" : ""}
                </option>
              ))}
            </select>
          </InlineField>
          {!isApiSearch ? (
            <p className="settings-cap-field-note">
              {searchProvider === "openalex"
                ? "OpenAlex 学术索引，无需 API Key。"
                : searchProvider === "multi_academic"
                  ? "multi_academic 并行 arXiv/CrossRef/PMC/OpenAlex/Semantic Scholar，无需 Key。"
                  : "native 使用 DuckDuckGo HTML 检索，无需 API Key。"}
            </p>
          ) : null}
          <div className="settings-cap-params-grid">
            <InlineField label="检索条数" htmlFor={`${cap.capability_id}-max`}>
              <input
                id={`${cap.capability_id}-max`}
                className="input"
                type="number"
                min={1}
                max={80}
                value={Number(params.search_max_results ?? 20)}
                onChange={(e) =>
                  setParams((p) => ({ ...p, search_max_results: Number(e.target.value) }))
                }
              />
            </InlineField>
            <InlineField label="失败重试" htmlFor={`${cap.capability_id}-retry`}>
              <input
                id={`${cap.capability_id}-retry`}
                className="input"
                type="number"
                min={0}
                max={3}
                value={Number(params.search_retry_count ?? 3)}
                onChange={(e) =>
                  setParams((p) => ({ ...p, search_retry_count: Number(e.target.value) }))
                }
              />
            </InlineField>
            {searchProvider === "tavily" ? (
              <InlineField
                label="检索深度"
                htmlFor={`${cap.capability_id}-depth`}
                tip={searchDepthTip}
              >
                <select
                  id={`${cap.capability_id}-depth`}
                  className="input settings-select"
                  value={String(params.search_depth ?? "advanced")}
                  onChange={(e) => setParams((p) => ({ ...p, search_depth: e.target.value }))}
                >
                  <option value="basic">basic — 更快、结果较少</option>
                  <option value="advanced">advanced — 更深、更慢</option>
                </select>
              </InlineField>
            ) : null}
          </div>
          <InlineField
            label="包含域名"
            htmlFor={`${cap.capability_id}-inc`}
            tip={CAP_TIPS.include_domains}
          >
            <textarea
              id={`${cap.capability_id}-inc`}
              className="input settings-textarea-compact"
              rows={4}
              placeholder="每行一个域名，如 arxiv.org"
              value={domainsToText(params.include_domains)}
              onChange={(e) =>
                setParams((p) => ({ ...p, include_domains: parseDomains(e.target.value) }))
              }
            />
          </InlineField>
          <InlineField
            label="排除域名"
            htmlFor={`${cap.capability_id}-exc`}
            tip={CAP_TIPS.exclude_domains}
          >
            <textarea
              id={`${cap.capability_id}-exc`}
              className="input settings-textarea-compact"
              rows={3}
              placeholder="每行一个域名"
              value={domainsToText(params.exclude_domains)}
              onChange={(e) =>
                setParams((p) => ({ ...p, exclude_domains: parseDomains(e.target.value) }))
              }
            />
          </InlineField>
          <div className="settings-cap-card__checks">
            <InlineCheck
              label="强制域名白名单过滤"
              checked={Boolean(params.enforce_domain_filter ?? true)}
              onChange={(checked) =>
                setParams((p) => ({ ...p, enforce_domain_filter: checked }))
              }
              tip={CAP_TIPS.enforce_domain_filter}
            />
            <InlineCheck
              label="启用 junk 过滤"
              checked={Boolean(params.enable_junk_filter ?? true)}
              onChange={(checked) => setParams((p) => ({ ...p, enable_junk_filter: checked }))}
              tip={CAP_TIPS.enable_junk_filter}
            />
          </div>
        </>
      );
    }
    if (cap.capability_id === "web_fetch") {
      const fetchProvider = String(params.fetch_provider ?? "native");
      const isNativeFetch = !fetchProviderNeedsCredential(fetchProvider);
      return (
        <>
          <InlineField
            label="抓取后端"
            htmlFor={`${cap.capability_id}-provider`}
            tip={CAP_TIPS.fetch_provider}
          >
            <select
              id={`${cap.capability_id}-provider`}
              className="input settings-select"
              value={fetchProvider}
              onChange={(e) =>
                setParams((p) => ({
                  ...p,
                  fetch_provider: e.target.value,
                }))
              }
            >
              {fetchProviders.map((opt) => (
                <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                  {opt.label}
                  {opt.disabled ? "（未配置 Key）" : ""}
                </option>
              ))}
            </select>
          </InlineField>
          {isNativeFetch ? (
            <p className="settings-cap-field-note">
              native 直连 HTTP（OJS / citation_pdf_url / PDF 解析），无需 web_fetch 凭据。连通测试见凭据页。
            </p>
          ) : (
            <p className="settings-cap-field-note">
              jina provider 需 API Key；不支持 native 的 PDF 解析选项。
            </p>
          )}
          {isNativeFetch ? (
            <InlineField
              label="PDF 解析"
              htmlFor={`${cap.capability_id}-pdf-backend`}
              tip={CAP_TIPS.pdf_extract_backend}
            >
              <select
                id={`${cap.capability_id}-pdf-backend`}
                className="input settings-select"
                value={String(params.pdf_extract_backend ?? "pymupdf4llm")}
                onChange={(e) =>
                  setParams((p) => ({ ...p, pdf_extract_backend: e.target.value }))
                }
              >
                <option value="pypdf">pypdf（默认，MIT）</option>
                <option value="pymupdf4llm">pymupdf4llm（Markdown/表格更佳）</option>
              </select>
            </InlineField>
          ) : null}
          {String(params.pdf_extract_backend ?? "pymupdf4llm") === "pymupdf4llm" && isNativeFetch ? (
            <p className="settings-cap-field-note">
              pymupdf4llm 基于 PyMuPDF（Artifex）。商业使用需 Artifex 许可证；可选：{" "}
              <code>pip install pymupdf4llm</code>
            </p>
          ) : null}
          <div className="settings-cap-params-grid">
            <InlineField label="抓取篇数" htmlFor={`${cap.capability_id}-urls`}>
              <input
                id={`${cap.capability_id}-urls`}
                className="input"
                type="number"
                min={1}
                max={50}
                value={Number(params.max_fetch_urls ?? 5)}
                onChange={(e) =>
                  setParams((p) => ({ ...p, max_fetch_urls: Number(e.target.value) }))
                }
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
                onChange={(e) =>
                  setParams((p) => ({ ...p, fetch_parallel: Number(e.target.value) }))
                }
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
                onChange={(e) =>
                  setParams((p) => ({ ...p, fetch_timeout_sec: Number(e.target.value) }))
                }
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
                onChange={(e) =>
                  setParams((p) => ({ ...p, fetch_retry_count: Number(e.target.value) }))
                }
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
                onChange={(e) =>
                  setParams((p) => ({ ...p, max_source_chars: Number(e.target.value) }))
                }
              />
            </InlineField>
          </div>
        </>
      );
    }
    if (cap.capability_id === "orchestrator") {
      return null;
    }
    if (cap.capability_id === "literature_source") {
      return null;
    }
    return null;
  };

  const paramsEl = renderParams();
  const moduleTip = capabilityModuleTip(cap.capability_id);

  return (
    <div className="settings-cred-row settings-list-row">
      <SettingToolbar
        title={
          <span className="settings-cap-card__title-row">
            {capabilityDisplayTitle(cap)}
            {moduleTip ? <FieldTip title={moduleTip} /> : null}
          </span>
        }
        titleMuted={false}
        feedback={rowMsg}
        feedbackOk={feedbackOk(rowMsg)}
        actions={
          <button
            type="button"
            className="btn-primary btn-sm"
            onClick={() => void save()}
            disabled={saving || !dirty}
          >
            {saving ? <Spin size="small" /> : null}
            保存
          </button>
        }
      />

      {needsRef ? (
        <InlineField
          label={refLabel}
          htmlFor={`${cap.capability_id}-ref`}
          tip={instanceTip}
        >
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
    void loadAdminBootstrap()
      .then((boot) => {
        setCaps(boot.caps);
        setCredentials(boot.credentials);
        setInstances(boot.instances);
      })
      .catch((e: unknown) => setMsg(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  const orderedCaps = useMemo(
    () =>
      sortCapabilities(
        caps.filter(
          (c) =>
            c.capability_id !== "prompts" &&
            SEARCH_FETCH_CAPABILITY_IDS.has(c.capability_id),
        ),
      ),
    [caps],
  );

  if (loading) {
    return (
      <SettingsListPanel>
        <SettingsListSkeleton rows={5} />
      </SettingsListPanel>
    );
  }

  return (
    <SettingsListPanel>
      <SettingsErrorMsg msg={msg} />

      <p className="settings-field-note settings-cap-section-note">
        文献来源、网络检索与网页抓取；编排与综述模型见「编排与综述」页。
      </p>

      <div className="settings-cap-list settings-cred-list--flat">
        {orderedCaps.map((c) => (
          <CapabilityCard
            key={c.capability_id}
            cap={c}
            credentials={credentials}
            instances={instances}
            onSaved={(saved) => {
              setCaps((prev) =>
                prev.map((x) => (x.capability_id === saved.capability_id ? saved : x)),
              );
            }}
          />
        ))}
      </div>
    </SettingsListPanel>
  );
}
