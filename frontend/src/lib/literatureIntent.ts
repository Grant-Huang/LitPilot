export const LITERATURE_INTENT_LABELS: Record<string, string> = {
  new_topic: "新主题 · 完整检索流程",
  subtopic_change: "子主题增改",
  append_urls: "追加文献链接",
  review_refine: "综述修订",
  query_corpus: "文献问答",
};

export function formatLiteratureIntentLabel(intent: string | undefined): string {
  if (!intent) return "";
  return LITERATURE_INTENT_LABELS[intent] ?? intent;
}
