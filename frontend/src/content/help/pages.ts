import type { HelpPage } from "./types";

export const quickStartPage: HelpPage = {
  id: "quick-start",
  title: "快速开始",
  category: "入门",
  summary: "3 分钟完成第一次文献综述",
  related: ["research-brief", "tavily-search", "artifact-panel"],
  body: `# 快速开始

## 1. 配置 API Key

打开 **管理员配置** → **凭据**：填写 Tavily、Jina、主 LLM 凭据；**能力** 页绑定到 web_search / web_fetch / review_main。

## 2. 发起综述

在 **聊天** 输入研究问题，例如：

「我要写 AI 原生 MOM 文献综述，包括四个方面：其一…其二…其三…其四…」

多 aspect 写法会自动拆子主题检索与分章写作（见 [[research-brief|如何写研究问题]]）。

## 3. 观看流式输出

- **左侧**：思考解说、阶段进度、正文流式增量
- **右侧**：**流程** / **大纲** / **综述** / **文献**（见 [[artifact-panel|右侧面板说明]]）

## 4. 多轮精化

材料不够 → 「再检索 trust + 知识图谱」  
只改某一章 → 「只重写第二章，改为表格，其余保留」（见 [[multi-turn|多轮精化]]）

## 5. 上传自有链接

输入框 **+** 上传 \`.txt\` / \`.csv\` / \`.json\` URL 列表；可与 Tavily 合并或仅用用户列表。`,
};

export const researchBriefPage: HelpPage = {
  id: "research-brief",
  title: "如何写研究问题",
  category: "写作",
  summary: "多 aspect brief 与检索效果",
  related: ["tavily-search", "multi-turn"],
  body: `# 如何写研究问题

## 推荐格式（多 aspect）

\`\`\`
我要写与 [主题] 有关的文献综述，包括 N 个方面：
其一，[子主题 A 的具体描述]。
其二，[子主题 B …]。
其三，…
其四，…
\`\`\`

系统会：

- 拆成 **N 个子主题**，各跑一轮检索
- 生成 **大纲**（导言 + N 章 + 综合讨论）
- **分章流式**写作后合并

## 示例：AI 原生 MOM

其四 aspect brief 可稳定拆出 4 个子主题；在 \`tavily_max_results=80\` 时合并命中约 **70** 条（去重后），实际抓取受 \`max_fetch_urls\` 限制（见 [[tavily-search|Tavily 与检索上限]]）。

## 单主题问题

简短问题仍可用；默认 **outline_mode=lite** 下走一次性生成。若希望强制分章，管理员 Prompts 中设 **outline_mode=full**。

## 边界与排除

在 brief 中写明「排除专利综述」「仅 2020 年后工业案例」等，会进入写作约束；检索词仍建议用英文关键词 augment（系统自动处理 MOM/MES）。`,
};

export const artifactPanelPage: HelpPage = {
  id: "artifact-panel",
  title: "右侧面板",
  category: "入门",
  summary: "流程、大纲、综述、文献四个 Tab",
  related: ["quick-start", "multi-turn"],
  body: `# 右侧面板说明

聊天页右侧 Artifact 区有四个 Tab（有内容时出现）：

## 流程

- 展示 **抓取之后** 的执行链：结构化 → 大纲 → 各章写作 → 后处理 → 交付
- 当前步骤与完成数（如 5/8 步）
- 检索与「理解问题」在 **左侧思考区**，不在此重复

## 大纲

- 多 aspect / 分章模式时出现
- 显示：研究问题、子主题检索式、章节与 **挂载文献数**
- 大纲确认后可切到此 Tab 对照正文结构

## 综述

- Markdown 流式预览（渲染 / 原文）
- 完成后可下载 \`review-latest.md\`

## 文献

- 本回合收录条目；点击综述中的 [n] 可跳转对应文献`,
};

export const multiTurnPage: HelpPage = {
  id: "multi-turn",
  title: "多轮精化",
  category: "写作",
  summary: "补充检索、章节修订、约束累积",
  related: ["research-brief", "faq"],
  body: `# 多轮精化

## 一轮只做一件事

| 目标 | 示例说法 |
|------|----------|
| 加文献 | 「再检索 manufacturing knowledge graph」 |
| 暂不写 | 「先补充文献，先不要生成综述」 |
| 改写法 | 「重点用表格对比，不要流水账」 |
| 只改一章 | 「**只重写第二章**，改为表格，**其余保留**」 |
| 问材料 | 「哪篇明确提了 OPC UA？」（短答，不重写全文） |

## 章节级修订（P0）

有大纲 + 上一版综述时，系统会：

- 解析「第二章 / 其二 / 第 N 章」
- **未指定章节**从上一版复用，不重复调用 LLM
- 指定章节注入 **上一版章稿** + **修订要求** 再流式生成

## 约束会记住

\`refine_gen\` 的写作要求写入会话 **gen_constraints**，后续轮次自动带上。请写 **可验证** 的要求（表格、必含小节、术语统一），避免「写更好一点」。`,
};

export const tavilySearchPage: HelpPage = {
  id: "tavily-search",
  title: "Tavily 检索与上限",
  category: "配置",
  summary: "命中数、抓取数、分主题检索",
  related: ["settings-guide", "faq"],
  body: `# Tavily 检索与上限

配置路径：**管理员配置 → 能力 → web_search**

## 核心参数

| 参数 | 含义 | 硬顶 |
|------|------|------|
| **tavily_max_results** | 多轮检索 **合并去重后** 的命中条数上限 | **80** |
| **max_fetch_urls**（web_fetch） | 实际抓取全文的 URL 数 | **50** |
| **include_domains** | 学术域名白名单 | 可关闭强制 |
| **enable_junk_filter** | 过滤低质量命中 | |
| **enable_query_expansion** | LLM 扩展多条检索式 | 与「多子主题检索」并存时，**多 aspect 优先分 4 轮** |

## 为什么以前「查不出」、现在可以？

- **以前**：整段 brief 压成 **一条** query，长中文多 aspect 召回差；默认只取 **8** 条
- **现在**：「其一…其四」拆 **4 条** query + MOM/MES 英文 augment，分轮合并

## 四 aspect MOM 实测参考

| 设置 | 合并命中 | 抓取 |
|------|----------|------|
| max_results=20 | ~19 | ≤ max_fetch_urls（如 8） |
| max_results=80 | ~70（去重） | ≤ max_fetch_urls |

**检索命中 ≠ 全文**：要提高材料量，需 **同时** 提高 \`tavily_max_results\` 与 \`max_fetch_urls\`。

## 推荐（大型综述）

- \`tavily_max_results\`：40–80
- \`max_fetch_urls\`：15–25
- \`outline_mode\`：lite（Prompts 页）
- \`enable_paper_attributes\`：开`,
};

export const settingsGuidePage: HelpPage = {
  id: "settings-guide",
  title: "设置导览",
  category: "配置",
  summary: "个人设置与管理员能力",
  related: ["tavily-search"],
  body: `# 设置导览

## 个人设置

- **引用格式**：APA / ACM
- **计划确认**：预留；开启后可在计划阶段暂停

## 管理员配置

| 页面 | 内容 |
|------|------|
| 凭据 | Tavily、Jina、LLM API Key |
| 实例 | 主模型、编排模型 |
| 能力 | web_search、web_fetch、literature_source、orchestrator |
| Prompts | 综述 System Prompt、文献结构化、**outline_mode**、**post_refine_mode** |

### outline_mode

- **关闭**：一次性写全文
- **智能（推荐）**：多 aspect 自动分章
- **始终分章**：单主题也分导言/正文/结论

### post_refine_mode

- **轻量校验**：去套话、缺节检测（默认）
- **关闭**：直接交付 LLM 原文`,
};

export const faqPage: HelpPage = {
  id: "faq",
  title: "常见问题",
  category: "疑难",
  summary: "检索、生成、修订",
  related: ["tavily-search", "multi-turn"],
  body: `# 常见问题

## 检索结果很少？

1. 提高 **tavily_max_results**（≤80）和 **max_fetch_urls**（≤50）
2. 用 **多 aspect** brief 触发分主题检索
3. 检查域名白名单是否过窄
4. 确认 Tavily Key 有效

## 综述与大纲章节对不上？

看右侧 **大纲** Tab 挂载数；某章 0 篇挂载却写得很满 → 先 \`expand_search\` 补该子主题，再 \`refine_gen\`。

## 只想改一章，全文被重写？

说明「**只重写第 N 章 / 其二，其余保留**」；需已有上一版综述 + 大纲。

## 流式中断？

可 Abort 后下轮用更窄的章节修订；已抓取语料保留在会话中。

## 数据存在哪？

本地 \`backend/data/\`：会话、文献库、综述 artifact。退出菜单只清本机 UI 偏好，不删服务端文件。`,
};
