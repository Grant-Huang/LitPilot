/** 能力绑定页字段说明（悬停 tip 用） */

export const CAP_TIPS = {
  search_provider:
    "检索后端：multi_academic 并行 arXiv/CrossRef/PMC/OpenAlex/Semantic Scholar（默认，无需 Key）；可在凭据页配置 Semantic Scholar Key 提升 SS 配额；Tavily/Brave 需 API Key。",
  search_depth_basic: "basic：更快、结果较少。",
  search_depth_advanced: "advanced：更深检索（仅 Tavily），结果更全、更慢。",
  enforce_domain_filter:
    "开启后只保留「包含域名」白名单内的命中；关闭后仍检索但不做域名硬过滤（澄清轮可临时关闭）。",
  enable_junk_filter:
    "过滤明显非论文页（教程、新闻聚合、下载站等），减少 junk 进入抓取队列。",
  include_domains: "每行一个域名；与「强制域名白名单」配合时作为允许列表。",
  exclude_domains: "每行一个域名；命中这些域名的结果会被剔除。",

  fetch_provider:
    "native：直连 HTTP + PDF 解析，无需 Jina。jina：Jina Reader 渲染 Markdown，需凭据页配置 Key。",
  pdf_extract_backend:
    "pypdf：轻量纯 Python。pymupdf4llm：表格/Markdown 更好，商业使用需 Artifex 许可。",

  orchestrator_instance:
    "编排模型（planner）：负责理解问题、检索式、阶段解说、网页摘要、文献结构化等。",
  review_instance:
    "综述主模型（review）：负责语料问答、矩阵与分章/全文综述撰写；通常选更强、上下文更大的模型。",
  orchestrator_reasoning:
    "仅对 MiniMax 等原生 reasoning 通道有意义；编排任务以 JSON 与短解说为主，默认关闭即可。OpenAI 等模型通常无效果。",
  orchestrator_tokens: "每个解说/checkpoint 单次 LLM 调用的 max_tokens 上限；过小可能导致 JSON 截断。",
} as const;

export const CAPABILITY_ORDER = [
  "literature_source",
  "web_search",
  "web_fetch",
] as const;

export const SEARCH_FETCH_CAPABILITY_IDS = new Set<string>(CAPABILITY_ORDER);

export const CAPABILITY_SUBTITLE: Partial<Record<string, string>> = {
  orchestrator: "编排模型：规划、检索式、阶段解说、网页摘要等",
  review_main: "综述模型：语料问答、矩阵与分章/全文撰写",
};

export function capabilityModuleTip(capId: string): string | undefined {
  const modules: Record<string, string[]> = {
    orchestrator: [
      "理解问题与路由",
      "检索式精炼 / 澄清",
      "检索扩展",
      "阶段解说",
      "网页分块摘要",
      "文献结构化",
    ],
    review_main: ["语料问答", "文献矩阵", "分章综述", "全文流式撰写"],
  };
  const list = modules[capId];
  if (!list?.length) return undefined;
  return `使用该实例的模块：\n${list.map((m) => `· ${m}`).join("\n")}`;
}

export function sortCapabilities<T extends { capability_id: string }>(items: T[]): T[] {
  const order = new Map(CAPABILITY_ORDER.map((id, i) => [id, i]));
  return [...items].sort(
    (a, b) =>
      (order.get(a.capability_id as (typeof CAPABILITY_ORDER)[number]) ?? 99) -
      (order.get(b.capability_id as (typeof CAPABILITY_ORDER)[number]) ?? 99),
  );
}
