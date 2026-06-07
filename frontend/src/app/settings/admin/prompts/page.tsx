"use client";

import { useEffect, useMemo, useState } from "react";

import { Spin } from "antd";

import {
  FieldTip,
  SettingToolbar,
  feedbackOk,
  SettingsListPanel,
  useUnsavedGuard,
} from "../_ui";

import { loadAdminBootstrap, invalidateAdminBootstrap } from "@/lib/settingsBootstrap";
import {
  instanceOptions,
  promptMaxTokensParam,
} from "@/lib/promptGroupBindings";
import { SettingsListSkeleton, errorMessage } from "../../_shared";
import { toastError } from "@/lib/toastFeedback";

import {
  settingsApiV2,
  type PromptTemplateMeta,
  type SystemCapability,
  type SystemInstance,
} from "@/lib/settingsApiV2";

const PROMPTS_HINT =
  "留空表示使用内置默认。自定义 JSON 类提示词若缺少输出契约字段，保存后运行时会自动追加契约段。";

const STAGE_MAP: Record<string, string> = {
  orchestrator: "orchestrate",
  router: "orchestrate",
  assessor: "orchestrate",
  search: "search",
  pipeline: "fetch",
  generation: "generate",
};

const STAGE_LABELS: Record<string, string> = {
  orchestrate: "意图理解与编排",
  search: "搜索文献",
  fetch: "获取文献",
  generate: "创建综述",
};

const STAGE_ORDER: readonly string[] = [
  "orchestrate",
  "search",
  "fetch",
  "generate",
];

function promptInstanceKey(key: string): string {
  return `${key}_instance_id`;
}

function stageMeta(
  meta: PromptTemplateMeta[],
): { id: string; label: string; items: PromptTemplateMeta[] }[] {
  const map = new Map<string, PromptTemplateMeta[]>();
  for (const item of meta) {
    const stage = STAGE_MAP[item.group];
    if (!stage) continue;
    const list = map.get(stage) || [];
    list.push(item);
    map.set(stage, list);
  }
  return STAGE_ORDER.filter((id) => map.has(id)).map((id) => ({
    id,
    label: STAGE_LABELS[id],
    items: map.get(id) || [],
  }));
}

function paramsEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export default function AdminPromptsPage() {
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [caps, setCaps] = useState<SystemCapability[]>([]);
  const [instances, setInstances] = useState<SystemInstance[]>([]);
  const [saving, setSaving] = useState(false);
  const [meta, setMeta] = useState<PromptTemplateMeta[]>([]);
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [templates, setTemplates] = useState<Record<string, string>>({});
  const [savedTemplates, setSavedTemplates] = useState<Record<string, string>>({});
  const [promptParams, setPromptParams] = useState<Record<string, unknown>>({});
  const [savedPromptParams, setSavedPromptParams] = useState<Record<string, unknown>>({});
  const [promptInstances, setPromptInstances] = useState<Record<string, string>>({});
  const [savedPromptInstances, setSavedPromptInstances] = useState<Record<string, string>>({});
  const [orchRefId, setOrchRefId] = useState("");
  const [savedOrchRefId, setSavedOrchRefId] = useState("");
  const [reviewRefId, setReviewRefId] = useState("");
  const [savedReviewRefId, setSavedReviewRefId] = useState("");
  const [savingPrompt, setSavingPrompt] = useState<string | null>(null);
  const [promptMsgs, setPromptMsgs] = useState<Record<string, string>>({});
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    orchestrate: true,
    generate: true,
  });

  const orchestratorCap = useMemo(
    () => caps.find((c) => c.capability_id === "orchestrator") || null,
    [caps],
  );
  const reviewCap = useMemo(
    () => caps.find((c) => c.capability_id === "review_main") || null,
    [caps],
  );
  const promptsCap = useMemo(
    () => caps.find((c) => c.capability_id === "prompts") || null,
    [caps],
  );
  const stages = useMemo(() => stageMeta(meta), [meta]);
  const instOpts = useMemo(() => instanceOptions(instances), [instances]);

  const templatesDirty = useMemo(() => {
    const keys = new Set([...Object.keys(templates), ...Object.keys(savedTemplates)]);
    for (const key of keys) {
      if ((templates[key] || "") !== (savedTemplates[key] || "")) return true;
    }
    return false;
  }, [templates, savedTemplates]);

  const promptInstancesDirty = useMemo(() => {
    const keys = new Set([
      ...Object.keys(promptInstances),
      ...Object.keys(savedPromptInstances),
    ]);
    for (const key of keys) {
      if ((promptInstances[key] || "") !== (savedPromptInstances[key] || ""))
        return true;
    }
    return false;
  }, [promptInstances, savedPromptInstances]);

  const dirty =
    templatesDirty ||
    promptInstancesDirty ||
    !paramsEqual(promptParams, savedPromptParams) ||
    orchRefId !== savedOrchRefId ||
    reviewRefId !== savedReviewRefId;

  useUnsavedGuard(dirty);

  useEffect(() => {
    void Promise.all([loadAdminBootstrap(), settingsApiV2.getPromptDefaults()])
      .then(([boot, defRes]) => {
        const items = boot.caps;
        setCaps(items);
        setInstances(boot.instances);
        setMeta(defRes.meta || []);
        setDefaults(defRes.defaults || {});

        const orch = items.find((c) => c.capability_id === "orchestrator");
        const review = items.find((c) => c.capability_id === "review_main");
        const prompts = items.find((c) => c.capability_id === "prompts");

        const orchId = String(orch?.primary_ref?.id || "");
        setOrchRefId(orchId);
        setSavedOrchRefId(orchId);
        const reviewId = String(review?.primary_ref?.id || "");
        setReviewRefId(reviewId);
        setSavedReviewRefId(reviewId);

        const params = (prompts?.params || {}) as Record<string, unknown>;
        setPromptParams({ ...params });
        setSavedPromptParams({ ...params });

        const loaded: Record<string, string> = {};
        const loadedInstances: Record<string, string> = {};
        for (const item of defRes.meta || []) {
          loaded[item.key] = String(params[item.key] || "");
          const instKey = promptInstanceKey(item.key);
          loadedInstances[item.key] = String(params[instKey] || "");
        }
        setTemplates(loaded);
        setSavedTemplates({ ...loaded });
        setPromptInstances(loadedInstances);
        setSavedPromptInstances({ ...loadedInstances });
      })
      .catch((e: unknown) => setMsg(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  const onSave = async () => {
    if (!promptsCap) return;
    setSaving(true);
    setMsg("");
    try {
      const orchPrimary =
        orchRefId && orchestratorCap
          ? ({ kind: "instance", id: orchRefId } as Record<string, unknown>)
          : null;
      const reviewPrimary =
        reviewRefId && reviewCap
          ? ({ kind: "instance", id: reviewRefId } as Record<string, unknown>)
          : null;

      const allParams: Record<string, unknown> = {
        ...(promptsCap.params || {}),
        ...promptParams,
        ...templates,
      };
      for (const [key, instId] of Object.entries(promptInstances)) {
        if (instId) {
          allParams[promptInstanceKey(key)] = instId;
        }
      }

      const saves: Promise<SystemCapability>[] = [
        settingsApiV2.updateCapability("prompts", { params: allParams }),
      ];
      if (orchestratorCap) {
        saves.push(
          settingsApiV2.updateCapability("orchestrator", {
            primary_ref: orchPrimary,
            params: orchestratorCap.params || {},
          }),
        );
      }
      if (reviewCap) {
        saves.push(
          settingsApiV2.updateCapability("review_main", {
            primary_ref: reviewPrimary,
          }),
        );
      }

      const savedList = await Promise.all(saves);
      invalidateAdminBootstrap();
      setCaps((prev) => {
        const byId = new Map(savedList.map((c) => [c.capability_id, c]));
        return prev.map((c) => byId.get(c.capability_id) || c);
      });
      setSavedTemplates({ ...templates });
      setSavedPromptParams({ ...promptParams });
      setSavedOrchRefId(orchRefId);
      setSavedReviewRefId(reviewRefId);
      setSavedPromptInstances({ ...promptInstances });
      setMsg("已保存");
    } catch (e: unknown) {
      const text = errorMessage(e);
      setMsg(text);
      toastError(text);
    } finally {
      setSaving(false);
    }
  };

  const onSavePrompt = async (promptKey: string) => {
    if (!promptsCap) return;
    setSavingPrompt(promptKey);
    try {
      const params: Record<string, unknown> = {};
      params[promptKey] = templates[promptKey] || "";
      const tokenParam = promptMaxTokensParam(promptKey);
      if (promptParams[tokenParam] !== undefined) {
        params[tokenParam] = promptParams[tokenParam];
      }
      if (promptInstances[promptKey]) {
        params[promptInstanceKey(promptKey)] = promptInstances[promptKey];
      }

      await settingsApiV2.updateCapability("prompts", { params });
      invalidateAdminBootstrap();

      setSavedTemplates((prev) => ({
        ...prev,
        [promptKey]: templates[promptKey] || "",
      }));
      setSavedPromptParams((prev) => {
        const next = { ...prev };
        next[tokenParam] = promptParams[tokenParam];
        return next;
      });
      setSavedPromptInstances((prev) => ({
        ...prev,
        [promptKey]: promptInstances[promptKey] || "",
      }));
      setPromptMsgs((prev) => ({ ...prev, [promptKey]: "已保存" }));
      setTimeout(() =>
        setPromptMsgs((prev) => {
          const next = { ...prev };
          delete next[promptKey];
          return next;
        }),
        2000,
      );
    } catch (e: unknown) {
      setPromptMsgs((prev) => ({ ...prev, [promptKey]: errorMessage(e) }));
    } finally {
      setSavingPrompt(null);
    }
  };

  const setTemplate = (key: string, value: string) => {
    setTemplates((prev) => ({ ...prev, [key]: value }));
  };

  const resetTemplate = (key: string) => {
    setTemplate(key, defaults[key] || "");
  };

  const setPromptInstance = (key: string, instanceId: string) => {
    setPromptInstances((prev) => ({ ...prev, [key]: instanceId }));
  };

  const toggleGroup = (id: string) => {
    setOpenGroups((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const perPromptDirty = (key: string): boolean => {
    const tDirty = (templates[key] || "") !== (savedTemplates[key] || "");
    const iDirty =
      (promptInstances[key] || "") !== (savedPromptInstances[key] || "");
    const tokenParam = promptMaxTokensParam(key);
    const pDirty =
      (promptParams[tokenParam] ?? undefined) !==
      (savedPromptParams[tokenParam] ?? undefined);
    return tDirty || iDirty || pDirty;
  };

  const saveButton = (
    <button
      type="button"
      className="btn-primary btn-sm"
      disabled={saving || !dirty || !promptsCap}
      onClick={() => void onSave()}
    >
      {saving ? <Spin size="small" /> : null}
      保存
    </button>
  );

  if (loading) {
    return (
      <SettingsListPanel className="settings-prompts">
        <SettingsListSkeleton rows={6} />
      </SettingsListPanel>
    );
  }

  return (
    <SettingsListPanel className="settings-prompts">
      <SettingToolbar
        title="编排与综述能力"
        feedback={msg}
        feedbackOk={feedbackOk(msg)}
        actions={saveButton}
      />

      <details className="settings-advanced settings-prompts__advanced">
        <summary className="settings-advanced__summary">编辑说明</summary>
        <div className="settings-advanced__body">
          <p className="settings-field-note">{PROMPTS_HINT}</p>
        </div>
      </details>

      {stages.map((stage) => (
        <section key={stage.id} className="settings-prompts__group">
          <div className="settings-prompts__group-head">
            <button
              type="button"
              className="settings-prompts__group-toggle"
              onClick={() => toggleGroup(stage.id)}
              aria-expanded={Boolean(openGroups[stage.id])}
            >
              {openGroups[stage.id] ? "▼" : "▶"} {stage.label}
            </button>
          </div>

          {openGroups[stage.id] ? (
            <div className="settings-prompts__group-body">
              {stage.items.map((item) => {
                const tokenParam = promptMaxTokensParam(item.key);
                const tokenDefault = item.default_max_tokens ?? 280;
                const tokenLimit = item.max_tokens_limit ?? 8000;
                const storedToken = promptParams[tokenParam];
                const tokenDisplay =
                  storedToken === undefined ||
                  storedToken === null ||
                  storedToken === ""
                    ? tokenDefault
                    : Number(storedToken);
                const promptDirty = perPromptDirty(item.key);
                const isSaving = savingPrompt === item.key;
                const promptMsg = promptMsgs[item.key];

                return (
                  <div key={item.key} className="settings-prompts__field">
                    <div className="settings-prompts__field-head">
                      <label htmlFor={`prompt-${item.key}`}>
                        {item.label}
                        {item.hint ? <FieldTip title={item.hint} /> : null}
                      </label>
                      <span className="settings-prompts__field-head-actions">
                        {promptMsg ? (
                          <span
                            className={
                              promptMsg === "已保存"
                                ? "settings-cred-row__feedback--ok"
                                : "settings-cred-row__feedback--err"
                            }
                          >
                            {promptMsg}
                          </span>
                        ) : null}
                        <button
                          type="button"
                          className="btn-primary btn-sm"
                          disabled={isSaving || !promptDirty}
                          onClick={() => void onSavePrompt(item.key)}
                        >
                          {isSaving ? <Spin size="small" /> : null}
                          保存
                        </button>
                        <button
                          type="button"
                          className="btn-ghost btn-sm"
                          onClick={() => {
                            resetTemplate(item.key);
                            setPromptParams((p) => {
                              const next = { ...p };
                              delete next[tokenParam];
                              return next;
                            });
                            setPromptInstance(item.key, "");
                          }}
                        >
                          恢复默认
                        </button>
                      </span>
                    </div>

                    <div className="settings-prompts__instance-row">
                      <select
                        id={`inst-${item.key}`}
                        className="input settings-select settings-prompts__instance-select"
                        value={promptInstances[item.key] || ""}
                        onChange={(e) =>
                          setPromptInstance(item.key, e.target.value)
                        }
                      >
                        <option value="">选择模型实例…</option>
                        {instOpts.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.label}
                          </option>
                        ))}
                      </select>

                      <input
                        id={`tok-${item.key}`}
                        className="input settings-prompts__token-input"
                        type="number"
                        min={80}
                        max={tokenLimit}
                        placeholder={String(tokenDefault)}
                        title={`单次调用的最大输出 token 数。默认 ${tokenDefault}，上限 ${tokenLimit}。`}
                        value={tokenDisplay}
                        onChange={(e) =>
                          setPromptParams((p) => ({
                            ...p,
                            [tokenParam]: Number(e.target.value),
                          }))
                        }
                      />
                      <span className="settings-prompts__token-label">
                        最大输出Token
                      </span>
                    </div>

                    <textarea
                      id={`prompt-${item.key}`}
                      className="input settings-textarea font-mono settings-prompts__editor"
                      value={templates[item.key] || ""}
                      onChange={(e) => setTemplate(item.key, e.target.value)}
                      spellCheck={false}
                      rows={
                        item.key === "review_system_prompt_template" ? 14 : 8
                      }
                    />
                    <p className="settings-prompts__hint">
                      最多 {item.max_len.toLocaleString()} 字符
                      {(templates[item.key] || "").length > 0
                        ? ` · 当前 ${(templates[item.key] || "").length}`
                        : " · 使用内置默认"}
                    </p>
                  </div>
                );
              })}
            </div>
          ) : null}
        </section>
      ))}

      {dirty ? (
        <div className="settings-prompts__save-bar">
          <span className="settings-prompts__save-bar-note">
            有未保存的修改
          </span>
          {saveButton}
        </div>
      ) : null}
    </SettingsListPanel>
  );
}
