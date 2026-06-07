"use client";

import { useEffect, useMemo, useState } from "react";

import { Spin } from "antd";

import {
  FieldTip,
  InlineCheck,
  InlineField,
  SettingToolbar,
  feedbackOk,
  SettingsListPanel,
  useUnsavedGuard,
} from "../_ui";

import { CAP_TIPS } from "@/lib/capabilityTips";
import { loadAdminBootstrap, invalidateAdminBootstrap } from "@/lib/settingsBootstrap";
import {
  instanceBindingLabel,
  instanceOptions,
  promptMaxTokensParam,
  PROMPT_GROUP_CAPABILITY,
  PROMPT_GROUP_INSTANCE_PARAM,
  PROMPT_GROUP_INSTANCE_TIPS,
  PROMPT_GROUP_ORDER,
  resolveGroupInstanceId,
} from "@/lib/promptGroupBindings";
import { SettingsListSkeleton, errorMessage } from "../../_shared";
import { toastError } from "@/lib/toastFeedback";

import {
  settingsApiV2,
  type PromptTemplateMeta,
  type SystemCapability,
  type SystemInstance,
} from "@/lib/settingsApiV2";

type OutlineMode = "off" | "lite" | "full";
type PostRefineMode = "off" | "lite";

const OUTLINE_MODE_OPTIONS: { value: OutlineMode; label: string }[] = [
  { value: "off", label: "关闭" },
  { value: "lite", label: "智能（推荐）" },
  { value: "full", label: "始终分章" },
];

const POST_REFINE_OPTIONS: { value: PostRefineMode; label: string }[] = [
  { value: "off", label: "关闭" },
  { value: "lite", label: "轻量校验" },
];

const OUTLINE_MODE_TIPS: Record<OutlineMode, string> = {
  off: "一次性生成整篇综述，不拆子主题检索与分章写作；适合短问题或调试。",
  lite: "检测到「其一、其二…」等多 aspect 提问时，自动拆子主题检索、挂载文献、按章节流式写作再合并；单主题仍一次性生成。",
  full: "无论是否多 aspect，均走大纲 + 分章写作（含导言/结论）；耗时与 token 更高，结构最可控。",
};

const POST_REFINE_TIPS: Record<PostRefineMode, string> = {
  off: "交付前不做规则后处理，综述原文直接保存。",
  lite: "拼接后去除套话结语、检测缺失章节、统计「待核实」标记，并推送 refine 报告 SSE。",
};

const PAPER_ATTR_TIP =
  "抓取后为每篇文献抽取 problem / method / findings 等字段，写入 paper_index，供大纲挂载与各章写作引用。";

const PROMPTS_HINT =
  "留空表示使用内置默认。自定义 JSON 类提示词若缺少输出契约字段，保存后运行时会自动追加契约段。";

function parseOutlineMode(raw: unknown): OutlineMode {
  const v = String(raw || "lite").toLowerCase();
  return v === "off" || v === "full" ? v : "lite";
}

function parsePostRefineMode(raw: unknown): PostRefineMode {
  return String(raw || "lite").toLowerCase() === "off" ? "off" : "lite";
}

function groupMeta(meta: PromptTemplateMeta[]): { id: string; label: string; items: PromptTemplateMeta[] }[] {
  const map = new Map<string, PromptTemplateMeta[]>();
  for (const item of meta) {
    const list = map.get(item.group) || [];
    list.push(item);
    map.set(item.group, list);
  }
  return PROMPT_GROUP_ORDER.filter((id) => map.has(id)).map((id) => ({
    id,
    label: map.get(id)?.[0]?.group_label || id,
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
  const [orchRefId, setOrchRefId] = useState("");
  const [savedOrchRefId, setSavedOrchRefId] = useState("");
  const [reviewRefId, setReviewRefId] = useState("");
  const [savedReviewRefId, setSavedReviewRefId] = useState("");
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    orchestrator: true,
    generation: true,
  });

  const orchestratorCap = useMemo(
    () => caps.find((c) => c.capability_id === "orchestrator") || null,
    [caps],
  );
  const reviewCap = useMemo(
    () => caps.find((c) => c.capability_id === "review_main") || null,
    [caps],
  );
  const promptsCap = useMemo(() => caps.find((c) => c.capability_id === "prompts") || null, [caps]);
  const groups = useMemo(() => groupMeta(meta), [meta]);
  const instOpts = useMemo(() => instanceOptions(instances), [instances]);

  const capRefSnapshot = useMemo(
    () => ({
      orchestrator: orchRefId,
      review_main: reviewRefId,
    }),
    [orchRefId, reviewRefId],
  );

  const templatesDirty = useMemo(() => {
    const keys = new Set([...Object.keys(templates), ...Object.keys(savedTemplates)]);
    for (const key of keys) {
      if ((templates[key] || "") !== (savedTemplates[key] || "")) return true;
    }
    return false;
  }, [templates, savedTemplates]);

  const dirty =
    templatesDirty ||
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
        for (const item of defRes.meta || []) {
          loaded[item.key] = String(params[item.key] || "");
        }
        setTemplates(loaded);
        setSavedTemplates({ ...loaded });
      })
      .catch((e: unknown) => setMsg(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  const setGroupInstanceId = (groupId: string, instanceId: string) => {
    const capId = PROMPT_GROUP_CAPABILITY[groupId];
    if (capId === "orchestrator") {
      setOrchRefId(instanceId);
      return;
    }
    if (capId === "review_main") {
      setReviewRefId(instanceId);
      return;
    }
    const paramKey = PROMPT_GROUP_INSTANCE_PARAM[groupId];
    if (!paramKey) return;
    setPromptParams((prev) => ({ ...prev, [paramKey]: instanceId }));
  };

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

      const saves: Promise<SystemCapability>[] = [
        settingsApiV2.updateCapability("prompts", {
          params: {
            ...(promptsCap.params || {}),
            ...promptParams,
            ...templates,
          },
        }),
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
      setMsg("已保存");
    } catch (e: unknown) {
      const text = errorMessage(e);
      setMsg(text);
      toastError(text);
    } finally {
      setSaving(false);
    }
  };

  const setTemplate = (key: string, value: string) => {
    setTemplates((prev) => ({ ...prev, [key]: value }));
  };

  const resetTemplate = (key: string) => {
    setTemplate(key, defaults[key] || "");
  };

  const toggleGroup = (id: string) => {
    setOpenGroups((prev) => ({ ...prev, [id]: !prev[id] }));
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

      <p className="settings-field-note settings-cap-section-note">
        按分组绑定模型实例；各提示词可单独设置 Token/阶段（未设时使用内置默认）。
      </p>

      <div className="settings-prompts__toggles">
        <InlineCheck
          label="启用文献结构化（AttributeTree lite）"
          checked={Boolean(promptParams.enable_paper_attributes ?? true)}
          onChange={(checked) =>
            setPromptParams((p) => ({ ...p, enable_paper_attributes: checked }))
          }
          tip={PAPER_ATTR_TIP}
        />

        <InlineField
          label="大纲驱动分章"
          htmlFor="outline-mode"
          tip={OUTLINE_MODE_TIPS[parseOutlineMode(promptParams.outline_mode)]}
        >
          <select
            id="outline-mode"
            className="input settings-prompts__select"
            value={parseOutlineMode(promptParams.outline_mode)}
            onChange={(e) =>
              setPromptParams((p) => ({ ...p, outline_mode: parseOutlineMode(e.target.value) }))
            }
          >
            {OUTLINE_MODE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </InlineField>

        <InlineField
          label="综述后处理"
          htmlFor="post-refine-mode"
          tip={POST_REFINE_TIPS[parsePostRefineMode(promptParams.post_refine_mode)]}
        >
          <select
            id="post-refine-mode"
            className="input settings-prompts__select"
            value={parsePostRefineMode(promptParams.post_refine_mode)}
            onChange={(e) =>
              setPromptParams((p) => ({
                ...p,
                post_refine_mode: parsePostRefineMode(e.target.value),
              }))
            }
          >
            {POST_REFINE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </InlineField>
      </div>

      <details className="settings-advanced settings-prompts__advanced">
        <summary className="settings-advanced__summary">编辑说明</summary>
        <div className="settings-advanced__body">
          <p className="settings-field-note">{PROMPTS_HINT}</p>
        </div>
      </details>

      {groups.map((group) => {
        const groupInstanceId = resolveGroupInstanceId(group.id, promptParams, capRefSnapshot);

        return (
          <section key={group.id} className="settings-prompts__group">
            <div className="settings-prompts__group-head">
              <button
                type="button"
                className="settings-prompts__group-toggle"
                onClick={() => toggleGroup(group.id)}
                aria-expanded={Boolean(openGroups[group.id])}
              >
                {openGroups[group.id] ? "▼" : "▶"} {group.label}
              </button>
            </div>

            {openGroups[group.id] ? (
              <div className="settings-prompts__group-body">
                <InlineField
                  label="模型实例"
                  htmlFor={`group-inst-${group.id}`}
                  tip={PROMPT_GROUP_INSTANCE_TIPS[group.id]}
                >
                  <select
                    id={`group-inst-${group.id}`}
                    className="input settings-select"
                    value={groupInstanceId}
                    onChange={(e) => setGroupInstanceId(group.id, e.target.value)}
                  >
                    <option value="">
                      {group.id === "router" ||
                      group.id === "search" ||
                      group.id === "assessor" ||
                      group.id === "pipeline"
                        ? "与编排实例相同（默认）"
                        : "选择模型实例…"}
                    </option>
                    {instOpts.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </InlineField>

                {group.items.map((item) => {
                  const tokenParam = promptMaxTokensParam(item.key);
                  const tokenDefault = item.default_max_tokens ?? 280;
                  const tokenLimit = item.max_tokens_limit ?? 8000;
                  const storedToken = promptParams[tokenParam];
                  const tokenDisplay =
                    storedToken === undefined || storedToken === null || storedToken === ""
                      ? tokenDefault
                      : Number(storedToken);

                  return (
                  <div key={item.key} className="settings-prompts__field">
                    <div className="settings-prompts__field-head">
                      <label htmlFor={`prompt-${item.key}`}>
                        {item.label}
                        {item.hint ? <FieldTip title={item.hint} /> : null}
                      </label>
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
                        }}
                      >
                        恢复默认
                      </button>
                    </div>
                    <p className="settings-prompts__hint settings-prompts__binding-note">
                      模型实例：继承「{group.label}」分组
                      {item.instance_binding
                        ? `（${instanceBindingLabel(item.instance_binding)}）`
                        : ""}
                    </p>
                    <InlineField
                      label="Token/阶段"
                      htmlFor={`tok-${item.key}`}
                      tip={`单次 LLM 调用的 max_tokens；默认 ${tokenDefault}，上限 ${tokenLimit}。`}
                    >
                      <input
                        id={`tok-${item.key}`}
                        className="input settings-prompts__token-input"
                        type="number"
                        min={80}
                        max={tokenLimit}
                        value={tokenDisplay}
                        onChange={(e) =>
                          setPromptParams((p) => ({
                            ...p,
                            [tokenParam]: Number(e.target.value),
                          }))
                        }
                      />
                    </InlineField>
                    <textarea
                      id={`prompt-${item.key}`}
                      className="input settings-textarea font-mono settings-prompts__editor"
                      value={templates[item.key] || ""}
                      onChange={(e) => setTemplate(item.key, e.target.value)}
                      spellCheck={false}
                      rows={item.key === "review_system_prompt_template" ? 14 : 8}
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
        );
      })}

      {dirty ? (
        <div className="settings-prompts__save-bar">
          <span className="settings-prompts__save-bar-note">有未保存的修改</span>
          {saveButton}
        </div>
      ) : null}
    </SettingsListPanel>
  );
}
