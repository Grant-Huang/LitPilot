import type { PromptTemplateMeta, SystemCapability } from "@/lib/settingsApiV2";

/** 提示词分组 ↔ 模型实例 ID 在 prompts.params 中的参数名（全部 6 组统一存储） */
export const PROMPT_GROUP_INSTANCE_PARAM: Record<string, string> = {
  orchestrator: "orchestrator_instance_id",
  router: "router_instance_id",
  search: "search_instance_id",
  assessor: "assessor_instance_id",
  generation: "generation_instance_id",
  pipeline: "pipeline_instance_id",
};

export const PROMPT_GROUP_CAPABILITY: Partial<Record<string, string>> = {
  orchestrator: "orchestrator",
  generation: "review_main",
};

export const PROMPT_GROUP_ORDER = [
  "orchestrator",
  "router",
  "search",
  "assessor",
  "generation",
  "pipeline",
] as const;

export const PROMPT_GROUP_INSTANCE_TIPS: Partial<Record<string, string>> = {
  orchestrator:
    "阶段解说与 Checkpoint A 理解；未绑定时编排流程不可用。组内各提示词共享此实例。",
  router: "续聊意图路由，可独立指定模型实例。",
  search: "检索式消歧、扩展与规范化。",
  assessor: "首轮 brief 评估与澄清。",
  generation:
    "综述撰写、分章、矩阵与语料问答；通常选更强、上下文更大的模型。",
  pipeline: "网页分块摘要与文献结构化提取。",
};

export function promptMaxTokensParam(key: string): string {
  return `${key}_max_tokens`;
}

const INSTANCE_BINDING_LABELS: Record<string, string> = {
  orchestrator: "编排解说",
  router: "路由",
  search: "检索",
  assessor: "评估澄清",
  review_main: "生成（review_main）",
  pipeline: "流水线",
};

export function instanceBindingLabel(binding: string | null | undefined): string {
  if (!binding) return "未绑定";
  return INSTANCE_BINDING_LABELS[binding] || binding;
}

export function instanceOptions(
  instances: Array<{ id: string; name: string; provider: string; model_name: string }>,
) {
  return instances.map((i) => ({
    id: i.id,
    label: `${i.name} · ${i.provider} · ${i.model_name}`,
  }));
}

export function capabilityRefIds(
  caps: SystemCapability[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const cap of caps) {
    const id = String(cap.primary_ref?.id || "");
    if (id) out[cap.capability_id] = id;
  }
  return out;
}

export function resolveGroupInstanceId(
  groupId: string,
  params: Record<string, unknown>,
  capRefs: Record<string, string>,
): string {
  // 优先从 prompts.params 读取，再回退到 capability primary_ref（向后兼容已存数据）
  const paramKey = PROMPT_GROUP_INSTANCE_PARAM[groupId];
  const fromParams = paramKey ? String(params[paramKey] || "") : "";
  if (fromParams) return fromParams;
  const capId = PROMPT_GROUP_CAPABILITY[groupId];
  if (capId) return capRefs[capId] || "";
  return "";
}

export function loadGroupInstances(
  meta: PromptTemplateMeta[],
  params: Record<string, unknown>,
  capRefs: Record<string, string>,
): Record<string, string> {
  const groups = new Set(meta.map((m) => m.group));
  const out: Record<string, string> = {};
  for (const group of groups) {
    out[group] = resolveGroupInstanceId(group, params, capRefs);
  }
  return out;
}

/** 空 stored 时使用内置默认，便于编辑区展示完整文案。 */
export function effectivePromptTemplate(
  stored: string | undefined,
  builtInDefault: string | undefined,
): string {
  const raw = (stored ?? "").trim();
  if (raw) return stored ?? "";
  return builtInDefault ?? "";
}

/** 与内置默认相同则存空串，运行时走 built-in。 */
export function promptTemplateForSave(
  displayed: string,
  builtInDefault: string | undefined,
): string {
  const text = displayed ?? "";
  const builtIn = builtInDefault ?? "";
  if (text === builtIn) return "";
  return text;
}

export function isPromptTemplateCustomized(
  displayed: string,
  builtInDefault: string | undefined,
): boolean {
  return promptTemplateForSave(displayed, builtInDefault) !== "";
}

/** 将分组实例 ID 写入 prompts.params（全部组统一存储）。 */
export function applyGroupInstanceToParams(
  groupId: string,
  instanceId: string,
  params: Record<string, unknown>,
): Record<string, unknown> {
  const next = { ...params };
  const paramKey = PROMPT_GROUP_INSTANCE_PARAM[groupId];
  if (instanceId) next[paramKey] = instanceId;
  else delete next[paramKey];
  return next;
}

export function primaryRefForGroup(
  groupId: string,
  instanceId: string,
): Record<string, unknown> | null {
  if (!PROMPT_GROUP_CAPABILITY[groupId] || !instanceId) return null;
  return { kind: "instance", id: instanceId };
}

export function groupItemsByGroup(
  items: PromptTemplateMeta[],
): Array<{ group: string; groupLabel: string; items: PromptTemplateMeta[] }> {
  const order: string[] = [];
  const map = new Map<string, PromptTemplateMeta[]>();
  for (const item of items) {
    if (!map.has(item.group)) {
      order.push(item.group);
      map.set(item.group, []);
    }
    map.get(item.group)!.push(item);
  }
  return order.map((group) => ({
    group,
    groupLabel: map.get(group)?.[0]?.group_label || group,
    items: map.get(group) || [],
  }));
}
