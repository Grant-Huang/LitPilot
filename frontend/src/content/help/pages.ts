import type { HelpPage } from "./types";

export const quickStartPage: HelpPage = {
  id: "quick-start",
  title: "快速开始",
  category: "入门",
  summary: "3 分钟完成第一次文献综述",
  related: ["research-brief", "artifact-panel", "tavily-search", "settings-guide"],
  body: `## 1. 配置凭据与能力

打开 **设置 → 管理员配置**：

- **凭据**：填写 Tavily、Jina、主 LLM 的 API Key
- **实例**：绑定主写作模型与编排（orchestrator）模型
- **能力**：将凭据挂到 \`web_search\`、\`web_fetch\`、\`review_main\`

详见 [[settings-guide|设置导览]]。

## 2. 发起综述

在 **聊天** 输入研究问题。推荐 **多 aspect** 写法，例如：

\`\`\`
我要写与 AI 原生 MOM 有关的文献综述，包括 4 个方面：
其一，定义框架与参考模型。
其二，信任机制与制造知识图谱。
其三，多智能体协作与微服务架构整合。
其四，从单体 MOM 向 AI 原生 MOM 的迁移路径。
\`\`\`

写法说明见 [[research-brief|如何写研究问题]]。系统会拆分子主题、分别检索，并在右侧展示流程与大纲。

## 3. 观看流式输出

- **左侧**：编排解说（思考区）、阶段时间线、工具调用、综述正文流式增量
- **右侧**：**流程** / **大纲** / **综述** / **文献** 四个 Tab（见 [[artifact-panel|右侧面板]]）

编排理解完成后，右侧 **流程** Tab 即会出现；澄清暂停时正文在左侧会话中展示，浏览器标题会显示 \`● 待补充\`（见 [[clarification|澄清与暂停]]）。

## 4. 多轮精化

- 材料不够 →「再检索 manufacturing knowledge graph」
- 只改某一章 →「**只重写第二章**，改为表格，**其余保留**」

详见 [[multi-turn|多轮精化]]。

## 5. 上传自有链接

输入框 **+** 可上传 \`.txt\` / \`.csv\` / \`.json\` URL 列表；可与 Tavily 合并，或设为「仅用用户列表」模式（能力页 \`literature_source\`）。`,
};

export const artifactPanelPage: HelpPage = {
  id: "artifact-panel",
  title: "右侧面板",
  category: "入门",
  summary: "流程、大纲、综述、文献四个 Tab",
  related: ["quick-start", "multi-turn", "clarification"],
  body: `聊天页右侧 **Artifact** 区按内容动态出现 Tab（无内容时不占位）。

## 流程

- **何时出现**：编排「理解研究问题」完成后即发布流程图，不必等到抓取开始
- **展示内容**：抓取之后的处理链——结构化 → 大纲 → 各章写作 → 后处理 → 交付
- **进度**：当前步骤与完成数（如 5/8 步）
- **说明**：检索与「理解问题」在 **左侧思考区** 展示，右侧聚焦抓取之后的流水线

## 大纲

- **何时出现**：多 aspect / 分章模式（智能或始终分章）下生成大纲后
- **内容**：研究问题、子主题检索式、章节标题与 **挂载文献数**
- 若开启 **计划确认**（个人设置），大纲生成后会暂停请你确认再撰写（见 [[clarification|澄清与暂停]]）

## 综述

- Markdown **渲染 / 原文** 切换
- 流式预览；完成后可下载 \`review-latest.md\`
- 若生成的是文献矩阵，文件名可能为 \`matrix-latest.md\`

## 文献

- 本回合收录的文献库条目
- 点击综述正文中的 \`[n]\` 可跳转到对应文献详情`,
};

export const researchBriefPage: HelpPage = {
  id: "research-brief",
  title: "如何写研究问题",
  category: "写作",
  summary: "多 aspect brief、检索式与编排理解",
  related: ["tavily-search", "multi-turn", "clarification"],
  body: `## 推荐格式（多 aspect）

\`\`\`
我要写与 [主题] 有关的文献综述，包括 N 个方面：
其一，[子主题 A 的具体描述]。
其二，[子主题 B …]。
其三，…
其四，…
\`\`\`

**其一 / 其二** 可以写在同一行（句号后接其二），系统会自动拆分。每个子方向建议 ≥ 8 字，并含可检索的技术词。

## 系统如何处理

- 拆成 **N 个子主题**，各跑一轮 Tavily 检索（多 aspect 优先于单次 query 扩展）
- 生成 **大纲**（导言 + N 章 + 综合讨论）
- **分章流式**写作后合并为完整综述

## 检索词建议

- brief 可用中文；系统会为 MOM/MES 等制造术语补充英文检索 augment
- 避免只写「写一篇综述」——编排无法提炼检索式时会触发 [[clarification|澄清与暂停]]
- 若已写清多 aspect 或编排已输出学术 \`search_query\`，**不会**再追问静态模板问题

## 单主题问题

简短单主题仍可用。默认 **智能分章** 下，材料足够时可能一次性写全文；若希望强制分章，在管理员 **Prompts** 将大纲模式设为「始终分章」。

## 边界与排除

在 brief 中写明「排除专利综述」「仅 2020 年后工业案例」等，会进入写作约束；检索仍建议包含英文技术关键词。`,
};

export const multiTurnPage: HelpPage = {
  id: "multi-turn",
  title: "多轮精化",
  category: "写作",
  summary: "补充检索、改写法、按章修订",
  related: ["research-brief", "artifact-panel", "faq"],
  body: `## 一轮只说一件事

| 你想做什么 | 示例说法 |
|------------|----------|
| 补充检索 | 「再检索 manufacturing knowledge graph」 |
| 先别写综述 | 「先补充文献，先不要生成综述」 |
| 调整写法 | 「重点用表格对比，不要流水账」 |
| 只改一章 | 「**只重写第二章**，改为表格，**其余保留**」 |
| 问已有材料 | 「哪篇明确提了 OPC UA？」（短答，不重写全文） |
| 文献矩阵 | 「生成文献综述矩阵 / synthesis matrix」 |

## 章节级修订

当会话已有 **大纲 + 上一版综述** 时：

- 系统解析「第二章 / 其二 / 第 N 章」等指代
- **未点名**的章节从上一版复用，不重复调用模型
- 指定章节注入 **上一版章稿 + 修订要求** 后再流式生成

## 写作约束会累积

调整写法类指令会写入会话 **写作约束**，后续轮次自动带上。请写 **可验证** 的要求（表格、必含小节、术语统一），避免「写更好一点」这类模糊表述。

## 与右侧 Tab 的配合

- 改结构前先看 **大纲** Tab 的章节与挂载文献数
- 某章 0 篇挂载却写得很满 → 先补充检索，再改写法或按章修订`,
};

export const tavilySearchPage: HelpPage = {
  id: "tavily-search",
  title: "Tavily 检索与上限",
  category: "配置",
  summary: "命中数、抓取数、分主题检索与域名",
  related: ["settings-guide", "research-brief", "faq"],
  body: `配置路径：**设置 → 管理员配置 → 能力 → web_search**（及 **web_fetch** 的抓取上限）。

## 核心参数

| 参数 | 含义 | 硬顶 |
|------|------|------|
| **tavily_max_results** | 多轮检索 **合并去重后** 的命中条数上限 | **80** |
| **max_fetch_urls**（web_fetch） | 实际抓取全文的 URL 数 | **50** |
| **include_domains** | 学术域名白名单 | 可关闭强制过滤 |
| **enable_junk_filter** | 过滤低质量命中 | 建议开启 |
| **enable_query_expansion** | 模型扩展多条检索式 | 与多 aspect 并存时，**多子主题分轮优先** |

## 多 aspect 为何更有效

- **以前**：整段 brief 压成 **一条** query，长中文多 aspect 召回差；默认只取少量命中
- **现在**：「其一…其四」拆 **多条** query，并对 MOM/MES 等做英文 augment，分轮合并去重

四 aspect 大型综述（如 AI 原生 MOM）在 \`tavily_max_results=80\`、\`max_fetch_urls=25\` 量级下，合并命中可达数十条；**实际全文数**受 \`max_fetch_urls\` 限制，与命中数不是同一概念。

## 检索命中 ≠ 全文材料

要提高材料量，需 **同时** 调高 \`tavily_max_results\` 与 \`max_fetch_urls\`。

## 推荐起点（大型综述）

| 场景 | tavily_max_results | max_fetch_urls |
|------|-------------------|----------------|
| 试水 | 20 | 8–12 |
| 标准四 aspect | 40–80 | 15–25 |

大纲模式、后处理模式在 [[settings-guide|设置导览]] 的 Prompts 页配置。`,
};

export const settingsGuidePage: HelpPage = {
  id: "settings-guide",
  title: "设置导览",
  category: "配置",
  summary: "个人偏好与管理员能力一览",
  related: ["tavily-search", "clarification", "tech-stack"],
  body: `## 个人设置

| 项 | 说明 |
|----|------|
| **引用格式** | APA / ACM，影响参考文献章节样式 |
| **计划确认** | 开启后，大纲生成完毕会 **暂停**，请你确认或修改后再撰写（与「大纲确认」澄清联动） |

## 管理员配置

| 页面 | 内容 |
|------|------|
| **凭据** | Tavily、Jina、LLM API Key（敏感项，仅存服务端或环境变量） |
| **实例** | 主写作模型、编排模型及对应凭据 |
| **能力** | \`web_search\`、\`web_fetch\`、\`literature_source\`、编排模式等运行时参数 |
| **Prompts** | 综述 System Prompt、文献结构化、大纲模式、后处理模式 |
| **概览 · 存储** | 持久化后端状态（file / turso）、Turso Database URL 与 Auth Token（敏感项，存服务端） |

### Turso 存储（概览页）

| 项 | 说明 |
|----|------|
| **持久化状态** | 显示当前 \`LITPILOT_STORAGE_BACKEND\` 与 Turso 是否已就绪 |
| **Database URL** | \`libsql://...\`；管理员保存可覆盖 env |
| **Auth Token** | 仅服务端保存，界面显示 \`***\` 尾号；留空提交表示不修改 |

**环境变量分工**：Vercel 后端 Dashboard 配置 Turso 三项（冷启动锚点）；本地开发在项目根 <code>.env</code> 填写相同键名（已 gitignore，勿提交）。概览页用于核对状态与运行期覆盖，不能单独替代 env。

### 大纲模式（Prompts）

| 模式 | 行为 |
|------|------|
| **关闭** | 一次性写全文 |
| **智能（推荐）** | 多 aspect 自动分章；单主题视材料而定 |
| **始终分章** | 单主题也拆导言 / 正文 / 结论 |

### 后处理模式（Prompts）

| 模式 | 行为 |
|------|------|
| **轻量校验** | 去套话、缺节检测（默认） |
| **关闭** | 直接交付模型原文 |

### 编排模式（能力 orchestrator）

| 模式 | 解说检查点 |
|------|------------|
| **lite** | 理解、检索后、抓取后、结构化后 |
| **full** | 含检索前、抓取中、引用后、生成前等 |

### 文献来源（literature_source）

| 模式 | 行为 |
|------|------|
| **merge** | Tavily 命中 + 用户上传 URL 合并抓取 |
| **user_only** | 跳过 Tavily，仅用用户列表 |

部署默认值与非敏感种子配置见 [[tech-stack|技术栈说明]]。`,
};

export const clarificationPage: HelpPage = {
  id: "clarification",
  title: "澄清与暂停",
  category: "疑难",
  summary: "何时暂停、如何继续、与编排的关系",
  related: ["faq", "settings-guide", "research-brief"],
  body: `系统在少数决策点会 **暂停本轮**，在左侧会话中展示追问；**不会**再弹重复 Toast，浏览器标题会显示 \`● 待补充…\` 作为未读提示。回复后自动继续；回复「取消」终止本轮。

## 何时会暂停

| 类型 | 触发条件 | 你该做什么 |
|------|----------|------------|
| **首轮补充** | 编排仍无法从 brief 提炼可检索主题（极短/纯「写综述」/ MOM 歧义等） | 用 1–2 句话补研究焦点或英文关键词；若已写清多 aspect brief，通常 **不会** 触发 |
| **检索无命中** | Tavily 零命中且未上传 URL | 回复「放宽检索」、给出更具体检索式，或粘贴论文 URL |
| **大纲确认** | 个人设置开启 **计划确认** 且大纲已生成 | 回复「确认」开始撰写，或直接说明要增删的章节 |

编排 checkpoint A 会在 JSON 中标注是否需要澄清；已给出多 aspect 或有效 \`search_query\` 时，\`needs_clarification\` 应为 false。

## 如何继续

- **补充说明**：直接输入文字，与上一轮问题合并理解
- **确认大纲**：「确认」「继续」「开始写」
- **取消**：「取消」「停止」「算了」

## 与右侧面板的关系

澄清暂停时 **流程** Tab 可能已展示（编排完成后发布）；材料检索尚未继续。补充并继续后，阶段时间线会从检索 onward 推进。

## 续聊与状态

- 暂停状态保存在会话元数据中；下一条用户消息会 **续跑** 而非新开回合
- 首轮补充后，同一澄清类型不会重复询问`,
};

export const faqPage: HelpPage = {
  id: "faq",
  title: "常见问题",
  category: "疑难",
  summary: "检索、生成、修订、澄清与数据",
  related: ["tavily-search", "multi-turn", "clarification", "tech-stack"],
  body: `## 检索结果很少？

1. 提高 **tavily_max_results**（≤80）和 **max_fetch_urls**（≤50）
2. 用 **多 aspect** brief（其一…其二…）触发分主题检索
3. 检查学术域名白名单是否过窄
4. 确认 Tavily Key 有效

详见 [[tavily-search|Tavily 检索与上限]]。

## 综述与大纲章节对不上？

看右侧 **大纲** Tab 各章 **挂载文献数**。某章 0 篇却写得很满 → 先补充该子主题检索，再调整写法或按章修订。

## 只想改一章，全文被重写？

说明「**只重写第 N 章 / 其二，其余保留**」；需已有上一版综述 + 大纲。见 [[multi-turn|多轮精化]]。

## 流式中断？

可点 **停止**；已抓取语料保留在会话中。下轮可窄化到单章修订继续。

## 系统突然停下来问我？

属于 [[clarification|澄清与暂停]]：首轮主题不清、检索零命中、或你开启了 **计划确认**。按会话内提示回复即可；标题栏 \`●\` 消失表示你已回复或继续。

## 写了很详细的 brief 仍被要求补充？

请确认 brief 含可拆分的「其一…其二…」或足够具体的技术词。单行多 aspect（句号后接其二）现已支持。若编排已在思考区列出子方向，不应再出现泛泛的静态追问——若仍出现，多为部署版本未更新。

## 中间会话变空、右侧仍有流程？

多为会话 ID 不同步（已修复：流结束会按服务端 session 重载消息）。仍异常时请刷新后从左侧会话列表点回该会话。

## 左侧「抓取网页全文」和阶段「抓取网页」不一样？

工具步骤用完整文案（区分制造 MOM 与 ML Mixture-of-Memories）；阶段时间线用 DAG 短标签，含义相同。

## 数据存在哪？

- **Vercel / 生产（推荐）**：会话、文献库、管理员配置等写入 **Turso**。在后端项目 Dashboard 配置 \`LITPILOT_STORAGE_BACKEND=turso\`、\`TURSO_DATABASE_URL\`、\`TURSO_AUTH_TOKEN\`（冷启动锚点）；概览页可核对或运行期覆盖。
- **本地开发**：默认 \`backend/data/\`（\`file\` 模式）；或在项目根 \`.env\`（gitignore）启用 Turso，键名与 Vercel 一致。

侧边栏 **退出** 仅清本机 UI 偏好（localStorage），**不删除** 服务端数据。`,
};

export const techStackPage: HelpPage = {
  id: "tech-stack",
  title: "技术栈说明",
  category: "参考",
  summary: "前后端框架、存储、SSE 与部署",
  related: ["settings-guide", "faq"],
  body: `LitPilot 基于 [MESO](https://github.com/Grant-Huang/MESO) 三栏交互框架，前后端分离。生产环境推荐 **Turso** 持久化；本地开发可用文件目录。

## 总体分层

| 层 | 技术 | 职责 |
|----|------|------|
| **UI 框架** | @meso.ai/ui、@meso.ai/types | 三栏布局、SSE 流式、Artifact、阶段时间线 |
| **LitPilot 前端** | Next.js 15、React 19 | 会话、文献库、设置、帮助中心 |
| **LitPilot 后端** | FastAPI、Python 3.12+ | literature_turn 编排、引用抽取、文件存储 |
| **外部服务** | Tavily、Jina Reader、LLM API | 学术检索、全文抓取、综述生成 |

## 前端

| 组件 | 说明 |
|------|------|
| **Next.js** | App Router，开发端口 **3002** |
| **React** | 19 |
| **Ant Design** | Modal、消息等 |
| **Tailwind CSS** | 补充样式 |
| **Vitest** | 单元测试 |

文献流经 **Task API**：\`POST /api/tasks\` 创建任务，\`GET /api/tasks/{id}/stream\` 订阅 SSE（支持断线重放）。直连 \`/api/chat/literature/execute\` 已废弃。

## 后端

| 组件 | 说明 |
|------|------|
| **FastAPI** | REST + SSE 文献流 |
| **uvicorn** | ASGI（默认 **8001**） |
| **httpx** | Tavily、Jina、LLM |
| **pytest** | 单元测试；\`scripts/test-gates.sh\` 含 Vercel 构建检查 |

核心模块：\`literature_turn\` → \`literature_turn_pipeline\`（检索→抓取→引用→结构化→大纲）→ \`literature_turn_generate\`（分章写作）→ \`literature_turn_finalize\`（交付与澄清暂停）。

## 存储

### Turso（Vercel / 生产推荐）

| 环境变量 | 说明 |
|----------|------|
| \`LITPILOT_STORAGE_BACKEND\` | \`turso\`（或 \`hybrid\`） |
| \`TURSO_DATABASE_URL\` | Turso libsql URL |
| \`TURSO_AUTH_TOKEN\` | 访问令牌（仅后端） |
| \`LITPILOT_TENANT_ID\` | 可选，多租户 ID（默认 \`default\`） |

| **配置来源** | Vercel / 本地 \`.env\` 为冷启动锚点；概览页为运行期覆盖 |
| **本地 \`.env\`** | 项目根、已 gitignore；与 Vercel 键名相同，便于联调 |

管理员 **概览** 页可保存 URL / Token 覆盖项；凭据、实例、能力等业务配置在 Turso 模式下同样写入 Turso。

### 本地文件（\`LITPILOT_STORAGE_BACKEND=file\`）

数据目录 \`backend/data/\`（\`LITPILOT_DATA_DIR\` 可覆盖）：

| 路径 | 内容 |
|------|------|
| \`config/\` | v2 凭据、实例、能力、个人偏好、\`system.storage.json\` |
| \`sessions/{id}/\` | meta、messages.jsonl、corpus、outline |
| \`refs/\` | 文献库 |
| \`artifacts/{id}/\` | 综述 Markdown、矩阵等 |

## 通信协议

- **REST**：\`{ status, data, message }\`
- **SSE（Meso v1.0）**：\`stage\`、\`think\`、\`text\`、\`artifact\`、\`tool_call\`、\`workflow_node\` 等
- **扩展事件**：\`literature_intent\`、\`literature_clarification\`、\`literature_outline\`、\`literature_subtopic_plan\` 等

## 开发与部署

| 项 | 说明 |
|----|------|
| Python | 3.12+（推荐 3.13） |
| Node.js | 18+，pnpm |
| 本地启动 | \`scripts/start-dev.sh\` |
| 测试门禁 | \`./scripts/test-gates.sh\` |
| Vercel | 前端 \`next build\`；后端 entrypoint \`app.main:app\`；敏感项走环境变量，非敏感默认见 \`deploy.defaults.json\` |

更多配置见 [[settings-guide|设置导览]]；排障见 [[faq|常见问题]]。`,
};
