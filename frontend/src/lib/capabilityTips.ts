/** 能力绑定页字段说明（悬停 tip 用） */

export const CAP_TIPS = {
  literature_source_merge:
    "合并：用户粘贴的 URL 与 web_search 检索结果一起进入抓取队列。仅用户列表：只用用户提供的链接，不调用 web_search。",
  literature_source_user_only:
    "仅使用对话中用户提供的链接，跳过网络检索。适合已有明确文献列表的场景。",

  search_provider:
    "检索后端：native 用 DuckDuckGo HTML（无需 Key）；OpenAlex 学术索引（无需 Key）；Tavily/Brave 需凭据页配置 API Key。",
  search_depth_basic: "basic：更快、结果较少。",
  search_depth_advanced: "advanced：更深检索（仅 Tavily），结果更全、更慢。",
  enforce_domain_filter:
    "开启后只保留「包含域名」白名单内的命中；关闭后仍检索但不做域名硬过滤（澄清轮可临时关闭）。",
  enable_junk_filter:
    "过滤明显非论文页（教程、新闻聚合、下载站等），减少 junk 进入抓取队列。",
  enable_query_expansion:
    "首轮检索前用 LLM 拆成多条 query 分别检索，再合并去重；适合多子主题综述，会增加 planner 调用与检索次数。",
  expansion_count: "检索扩展开启时，最多生成几条并行 query（不含主 query）。",
  include_domains: "每行一个域名；与「强制域名白名单」配合时作为允许列表。",
  exclude_domains: "每行一个域名；命中这些域名的结果会被剔除。",

  fetch_provider:
    "native：直连 HTTP + PDF 解析，无需 Jina。jina：Jina Reader 渲染 Markdown，需凭据页配置 Key。",
  pdf_extract_backend:
    "pypdf：轻量纯 Python。pymupdf4llm：表格/Markdown 更好，商业使用需 Artifex 许可。",

  orchestrator_instance:
    "编排模型（planner）：负责理解问题、检索式、阶段解说、网页摘要、文献结构化等；与下方「解说密度」无关。",
  review_instance:
    "综述主模型（review）：负责语料问答、矩阵与分章/全文综述撰写；通常选更强、上下文更大的模型。",
  orchestrator_mode:
    "控制流程中「思考区」阶段解说的多少，不是换模型。off=无解说；lite=关键节点；full=各阶段均有解说。",
  orchestrator_mode_off: "关闭阶段解说，仍执行检索/抓取/撰写（router JSON 仍走 planner 模型）。",
  orchestrator_mode_lite: "在理解、检索后、抓取后、结构化等关键节点输出简短解说。",
  orchestrator_mode_full: "检索前/后、抓取进度、引用、生成前等更多节点均解说。",
  orchestrator_reasoning:
    "若模型支持 reasoning 通道，将思考过程流入「思考区」；关闭则只显示可见叙述与 JSON。",
  orchestrator_tokens: "每个解说/checkpoint 单次 LLM 调用的 max_tokens 上限；过小可能导致 JSON 截断。",
} as const;

export const CAPABILITY_ORDER = [
  "literature_source",
  "web_search",
  "web_fetch",
  "orchestrator",
  "review_main",
] as const;

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
