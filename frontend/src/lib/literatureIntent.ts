export const LITERATURE_INTENT_LABELS: Record<string, string> = {
  new_topic: "新主题 · 完整检索流程",
  supplement: "补充文献",
  refine_gen: "调整综述要求",
  regen_only: "重新生成综述",
  expand_search: "扩展检索",
  retry_failed: "重试失败链接",
  query_corpus: "文献问答",
  manage_library: "文献库管理",
};

export function formatLiteratureIntentLabel(intent: string | undefined): string {
  if (!intent) return "";
  return LITERATURE_INTENT_LABELS[intent] ?? intent;
}
