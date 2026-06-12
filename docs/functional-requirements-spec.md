# LitPilot 功能需求说明书（复制开发版）

> 本文档面向**第三方开发团队**，目标是据此**从零复制开发一个功能等价的应用**。文档以"做什么、给用户看什么、交互如何、数据如何流动、如何持久化、异常如何处理"为主线，尽量给出具体的字段名、状态名、默认值、约束与端点契约。**行为契约必须一致**。

### 技术栈与底座（强约束）
- **前端**：以 **TypeScript 为主**，基本沿用原 LitPilot 技术栈（Next.js 15 + React 19）。
- **UI 底座**：使用 **MESO `@meso.ai/ui` 2.1.1**（npm）作为基础三栏布局与会话框底座（`@meso.ai/types` 2.1.x 配套）。侧栏品牌走 MESO 白牌 API（`sidebarLogo` / `sidebarTitle`），业务 UI 在 LitPilot 内实现。
- **后端**：FastAPI（沿用原实现）。
- **存储**：**初期不使用数据库，直接用本地文本文件**（JSON / JSONL / Markdown）+ filelock 并发安全；Turso/SQLite 为后续可选项，初期不启用。
- **品牌资源**：统一使用仓库 **`brand/` logo 资源包**（`brand/svg/*`、`brand/png/*`、`brand/react/LitPilotMark.tsx`、`brand/tokens.css` / `tokens.ts`）。favicon/PWA 用 `brand/snippets/head.html` 与 `brand/site.webmanifest`。**不得自造 logo**。

### 会话框交互总原则（强约束）
- 主会话框**不采用卡片（Card）形式**。除"执行状态/统计数据"在原位更新外，**所有文本输出一律流式追加**（append），按出现顺序自然向下生长。
- 会话框内容分三类、**各自独立设计且每类风格统一**：①消息正文；②思考内容；③工具执行脚本输出。其中**思考内容与工具执行输出默认折叠**，折叠态只滚动显示**最新一行**，点击展开/收起（详见 1.3）。
- **唯一例外**：**澄清卡**独立设计、**强制展开**（详见 1.4）。

---

## 0. 产品概述

### 0.1 定位
LitPilot 是一款面向科研人员的**文献综述助手**。用户用自然语言描述研究主题，系统自动完成：理解问题 → 学术检索 → 全文抓取 → 引用抽取 → 大模型综述生成 → 交付结构化产物（综述、文献矩阵、大纲），并把抽取到的引用沉淀进**文献库**。执行过程以**流式文本追加**的方式实时呈现（非卡片）。

### 0.2 三大界面
| 界面 | 路由 | 职责 |
|------|------|------|
| 主会话窗口 | `/chat` | 文献综述对话、流式执行过程、流式输出、右侧 Artifact 面板 |
| 文献库 | `/library` | 引用索引浏览、元数据编辑、按状态/标签筛选、引用复制导出 |
| 设置 - 个人 | `/settings/personal` | 个人偏好（引用格式固定 APA，已无可切换项） |
| 设置 - 管理员 | `/settings/admin/*` | 凭据、实例、能力（检索/抓取）、Prompts、存储 |

### 0.3 顶层数据流（一次综述）
```
用户输入主题
  → 创建 Task（POST /api/tasks）
  → SSE 流式执行：理解 → 检索 → 抓取 → 引用抽取 → 综述生成
  → 中间区流式追加：消息正文 / 思考内容（折叠）/ 工具执行输出（折叠）/ 执行状态原位更新
  → 产物落到 Artifact 面板（右）：综述 / 大纲（矩阵仅按用户显式要求生成）
  → 引用 upsert 进文献库
  → 会话与消息落盘为本地文本文件（无数据库）
```

### 0.4 统一 API 响应约定
除 SSE 流外，所有 REST 接口返回统一 JSON 结构：
```json
{ "status": "success|error", "data": {}, "message": "可选" }
```
（部分内部接口直接返回 `{ ok: boolean, error?: string, ... }`，复制时保持同一接口同一风格即可。）

---

## 1. 主会话窗口（`/chat`）

### 1.1 整体布局：四列结构
从左到右依次为：导航栏 / 会话列表 / 中间对话区 / 右侧 Artifact 面板。

```
┌ 导航(≈145px) ┬ 会话列表(≈260px) ┬ 中间对话区(flex) ┬ Artifact 面板 ┐
│              │                  │ 可滚动消息区     │ Tabs:         │
│              │                  │                  │ 大纲/综述/    │
│              │                  │                  │ 矩阵/文献     │
│              │                  ├──────────────────┤               │
│              │                  │ 输入器 Composer  │ (固定)        │
└──────────────┴──────────────────┴──────────────────┴───────────────┘
```

**宽度策略（必须遵循的体验目标，像素值可按实现微调）：**
- 左侧两栏固定宽度合计约 405px。
- 中间对话区主内容最大宽度：`min(72rem, max(42rem, 主列宽 × 0.68))`，即随窗口缩放但有 42rem 下限与 72rem 上限。
- Artifact 面板打开时宽度：`clamp(280px, 主列宽 - 内容宽 - 32px, 420px)`；打开时给布局根节点加修饰类（参考实现：`litpilot-layout--artifact-open`），主内容相应收窄。

### 1.2 会话列表（左侧第二栏）
- 列表项展示会话**标题**（首轮综述后由系统自动命名，见 1.10 `session_title` 事件）。
- 支持操作：新建会话、选择会话、重命名、删除、置顶（pin）。
- 置顶会话排在普通会话之前。
- **当前激活会话**持久化在前端本地存储键 `litpilot:active-session`；应用加载时自动恢复并打开该会话。
- 路由 `/chat/{sessionId}` 直接打开指定会话。

**相关后端接口：**
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/sessions` | 列出全部会话（含标题、置顶、时间戳） |
| `POST` | `/api/sessions` | 创建会话 |
| `GET` | `/api/sessions/{id}/messages` | 获取会话消息历史 |
| `POST` | `/api/sessions/{id}/messages` | 追加一条消息（持久化） |
| `PATCH/PUT` | `/api/sessions/{id}` | 重命名 / 置顶 |
| `DELETE` | `/api/sessions/{id}` | 删除会话 |

### 1.3 消息区与对话历史（流式追加，非卡片）

中间对话区是一条**自上而下单列的流式时间线**：用户消息与助手回合按时间顺序排列；助手回合内部由三类**独立设计的内容块**按产生顺序**流式追加**而成，不再包裹成卡片。

#### 1.3.1 空状态（欢迎屏）
当无任何消息且未在流式时显示欢迎屏：
- LitPilot 品牌标识（取自 `brand/` 资源包，如 `brand/react/LitPilotMark.tsx` 或 `brand/svg/lockup-stacked.svg`）。
- 引导语："描述研究主题，过程与思考在下方实时展开，综述与大纲在右侧 Artifact 面板查看。"
- 对齐方式可配置：居中或置顶。

#### 1.3.2 三类内容块（各自独立设计、每类风格统一）
助手回合内允许出现以下三类块，**每类有统一且互相区分的视觉风格**（字体/留白/底色/图标各成一套）：

| 内容类型 | 来源 | 默认展开态 | 折叠态行为 | 展开交互 |
|----------|------|------------|------------|----------|
| **① 消息正文** `body` | `text`（delivery=chat/process）流式增量、最终答复 | **始终展开** | — | — |
| **② 思考内容** `think` | `thinkContent` / think 流 | **默认折叠** | 只滚动显示**最新一行**（单行跑马/滚动） | 点击块首/展开按钮 → 完整多行；再点收起 |
| **③ 工具执行脚本输出** `tool` | `tool_call` / `tool_result`、检索/抓取/引用等脚本 stdout | **默认折叠** | 只滚动显示**最新一行** | 点击 → 完整输出（`<pre>` 等宽，保留换行）；再点收起 |

规则：
- 三类块**样式不可混用**：正文是阅读态排版；思考是弱化/灰调、可读但次要；工具输出是等宽/终端态。
- 折叠块在折叠态仅占**一行高度**，内部内容向上滚动、**只露出最新一行**，左侧有类型图标 + 标题（如"思考中…""检索脚本输出"）、右侧有展开角标（▸/▾）。
- 流式过程中折叠块的"最新一行"随增量实时刷新；流结束后保持折叠，用户可随时点开回看。
- **执行状态/统计数据**（如阶段名、命中数、进度 n/m、耗时）属于"原位更新"信息，显示在对应块的状态行上，就地覆盖刷新，**不作为新文本追加**。

#### 1.3.3 历史消息渲染规则（复现须与当初一致）
- 历史回合从持久化的 `messages.jsonl` 重建，**内容与样式须与当初会话完全一致**：三类块的划分、各块文本、折叠/展开的默认态、状态行统计、澄清卡（若有）一并复现。
- 为此，助手消息需把三类块及其元数据完整落盘（见 1.7.1 `blocks[]` 结构）；复现时按 `blocks` 顺序逐块还原，思考/工具块默认折叠、正文展开。
- 用户消息：纯文本，沿用 MESO 会话气泡风格。

#### 1.3.4 实时回合（流式中）
- 当前任务的回合实时追加在时间线末尾：正文块持续增量、思考/工具块以折叠单行滚动刷新、状态行原位更新。
- 含运行指示器（行内 spinner / 进度文本），不使用整块卡片包裹。

#### 1.3.5 自动滚动
- "贴底阈值" = 80px：`scrollHeight - scrollTop - clientHeight ≤ 80px` 视为用户在底部。
- 用户在底部时：新用户消息自动贴底；流式中随增量平滑滚动。
- 用户上滑阅读历史时：**不强制跳动**，保留阅读位置。
- 切换会话（reset key 变化）时：重新贴底（后台任务返回时见 1.7.3）。
- 用 ResizeObserver 监听容器尺寸变化（如 Artifact 面板开合导致主区宽变化）。
- 不在底部时显示"回到底部"悬浮按钮（FAB）。

### 1.4 执行过程的流式展示（非卡片）

> **流程的业务逻辑（意图路由、各阶段触发/分支、顺序）以 `docs/flow-card-logic-and-prompts.md` 为准**，本节只规定**展示形态**。注意：该文件名中的"流程卡"仅指后端阶段编号，**前端不渲染为卡片**，而是按下述流式块呈现。

#### 1.4.1 展示形态总则
执行过程不再拆成可折叠卡片，而是融入 1.3 的三类内容块：
- **阶段推进**：理解 → 检索 → 抓取 → 引用 → 结构化 → 大纲 → 综述生成等阶段，作为**状态行**在工具执行块的标题/状态位**原位更新**（阶段名 + 进度 + 耗时），不为每个阶段新开卡片。
- **脚本/工具输出**：检索、抓取、引用抽取等产生的过程明细，进入**工具执行脚本输出块**（默认折叠，只滚动显示最新一行；点击展开看全量）。
- **解说/叙述**：阶段解说等过程文本，作为**消息正文**的过程段流式追加，或并入思考块（按 delivery 区分）。

折叠态状态行示例（只显示最新一行，原位刷新统计）：
```
▸ 检索脚本输出 · 文献检索 3/5 PASS（by_source 并行）· 命中 142 · 24s
```
展开后（点击）可见完整明细，例如：
```
逻辑检索 · arXiv（21 篇）
混合检索 · OpenAlex（48 篇）
向量检索 · Semantic Scholar（73 篇）
抓取 43/150 · 已获取 12 · 超时 4 · 待入队 27
引用抽取 · 12 篇完成 · APA 格式化 · 3s
```

#### 1.4.2 阶段状态语义
- 状态：`pending | running | done | error`，对应状态行图标 ○ / ⟳ / ✓ / ⚠。
- 多子主题检索的层级明细（子主题 → 数据源 → 过滤结果）作为**工具执行块展开后的内容**呈现（折叠态仍只露最新一行），不再单独渲染为"检索进度树卡片"。

#### 1.4.3 回合收尾
- 回合结束后，在正文末尾追加一行**简要汇总文本**（流式追加，非卡片栏），如"检索纳入 47 篇 · 获取 42 篇 · 综述已生成"。
- 若存在综述/大纲产物但右侧 Artifact 面板未打开，在该汇总行内提供一个**内联文字链接**"查看综述"，点击打开面板（不使用独立 CTA 卡片）。
- **矩阵不在首轮自动生成**；仅当用户在后续对话显式要求时才生成（见 1.8）。

### 1.4A 澄清卡（独立设计，强制展开 —— 唯一卡片例外）
澄清是流式时间线中**唯一**以"卡片"形态独立设计的元素：
- **强制展开**，不可折叠；视觉上与三类内容块明显区分（独立边框/底色/标题"等待澄清"）。
- 触发：理解阶段 `confidence < 0.6`，或首轮 `plan_confirm` 计划确认（见 1.9）。
- 内容：澄清说明 + 2–3 个可点击的研究方向选项（或确认/调整）。用户选定后，澄清卡固化为历史记录的一部分（复现时同样强制展开）。
- 数据：来自 `literature_clarification` 事件（见 1.6.3）。

### 1.5 输入器（Composer）

底部输入区结构：URL/并行度元信息行 + 多行文本框 + 控制条（上传 / 活动提示 / 发送或停止）。

#### 1.5.1 文本输入
- 多行自适应文本框，最少 2 行，最多 6 行。
- 占位符："描述你的研究主题或综述问题…"。
- 回车发送；Shift+回车换行。
- 流式进行中禁用输入。

#### 1.5.2 链接上传
- "+"附件按钮，接受 `.txt/.csv/.json`，从中解析 http(s) 链接。
- **首轮（第 1 轮）禁用上传**（new_topic，须先用文字描述主题）；**第 2 轮起的追加轮次开启上传**（append_urls 可上传 URL 列表文件并追加文献）。
- 解析后超出 `max_fetch_urls`（来自设置，默认上限 50）时按设置保留前 N 条。
- 已选链接以可关闭标签显示"N 个链接"。
- Toast 反馈：
  - "已添加 N 个抓取链接"（成功）
  - "文件中共 M 条链接，已按当前设置保留前 N 条"（截断）
  - "未在文件中找到有效 http(s) 链接"（无链接）
  - "无法解析链接列表文件"（解析失败）

#### 1.5.3 发送 / 停止
- 发送启用条件：`(文本非空 或 (有链接 且 未禁用上传)) 且 非流式`。
- 流式进行中，发送按钮替换为"■ 停止"按钮，点击取消任务（DELETE/cancel 任务）。

#### 1.5.4 流式活动提示与并行度芯片
- **静默提示**：自上次 SSE 事件起的静默秒数 `silenceSec`：
  - < 5s：不提示。
  - 5–19s：level=waiting，显示"{阶段} - 已等待 N 秒"（◌）。
  - ≥ 20s：level=slow，显示变慢警告（⚠️）。
- **并行度芯片**（流式中只读展示）：从 `literature_search_plan` / `literature_progress` 事件提取，如"并行检索 5 个数据源""并行检索 3 个子主题""fetch 并行 3"。

### 1.6 流式与 SSE 数据流

#### 1.6.1 流阶段（前端计算）
`idle → pending（等待建任务/首字节）→ streaming → settling（收尾物化）→ done/error`。

#### 1.6.2 SSE 信封格式（参考 Meso v1.0）
```
event: extension
data: {"name":"literature_search_plan","version":"1.0","data":{...}}

event: stage
data: {"name":"文献检索","state":"active"}

event: artifact
data: {"id":"review-latest","lang":"markdown","delta":"# 综述\n\n","done":false}

event: text
data: {"delta":"设计…","delivery":"process"}

event: done
data: {}
```
事件类型至少包含：`extension`（自定义进度）、`stage`（阶段切换）、`artifact`（产物增量，含 review markdown / outline json / matrix）、`text`（聊天或流程文本增量，区分 delivery）、`done`、`error`。

#### 1.6.3 关键自定义扩展事件
| 事件名 | 载荷要点 | UI 用途 |
|--------|----------|---------|
| `literature_search_plan` | count, subtopics[], parallel_mode, source_parallel, topic_parallel | 并行度芯片、子主题列表 |
| `literature_subtopic_plan` | subtopics:[{id,title,search_query}] | 理解卡内计划视图 |
| `literature_search_pass_start` | pass_index, pass_total, query, topic_title | 检索 pass 进度 |
| `literature_search_source_start/_done` | source, label, topic_title, hits | 检索树节点 |
| `literature_subtopic_filter_done` | subtopic_id, kept_count, rejected_count | 子主题过滤摘要 |
| `literature_progress` | stage, elapsed_sec, parallel, in_flight | 活动提示 |
| `literature_fetch_start/_done` | url_count, completed | 抓取进度 |
| `literature_clarification` | kind（outline_confirm / search_zero 等） | 触发澄清卡 |
| `turn_start` | turn_index, intent | 重置回合累积 |
| `turn_end` | turn_index, summary | 收尾回合 |
| `session` | session_id | 后端绑定/改写会话 ID |
| `session_title` | session_id, title | 自动重命名，刷新会话列表 |

#### 1.6.4 流式实现要点（性能/健壮性）
- **rAF 批处理**：事件在帧间累积，每帧最多一次 React 提交；`done/error` 时同步落定。
- **看门狗**：收到响应头后若 120 秒无任何 chunk，判定上游冻结并自动 abort，避免永久 pending。
- **断点续传游标**：流地址支持 `?since=N`，按事件序号续传（`GET /api/tasks/{id}/stream?since=0`）。

### 1.7 任务与会话消息持久化（本地文本，无数据库）

#### 1.7.1 发送→执行→落盘流程
1. 用户发送 → `POST /api/tasks`（body: `{session_id, message, fetch_urls}`）→ 得 taskId。
2. 连接流 `GET /api/tasks/{taskId}/stream?since=0`。
3. 累积 SSE 事件，构建助手回合的 `blocks[]`（三类内容块）+ 执行轨迹。
4. 流结束（done）→ 物化为助手消息并落盘。
5. 持久化：`POST /api/sessions/{id}/messages`（用户消息与助手消息分别落盘）。
6. 回读校验：轮询直至消息出现或超时；回读失败时回退展示已物化的实时消息。

**助手消息结构（含三类块，供历史一致复现）：**
```jsonc
{
  "role": "assistant",
  "delivery": "process|chat|artifact",
  "blocks": [
    { "type": "body",  "text": "…正文 markdown…" },
    { "type": "think", "text": "…思考全文…", "collapsed": true },
    { "type": "tool",  "title": "检索脚本输出", "text": "…完整输出…",
      "status": "done", "stats": "命中 142 · 24s", "collapsed": true },
    { "type": "clarify", "force_open": true, "prompt": "…", "options": [ /* … */ ] }
  ],
  "execution_trace": { /* 阶段/工具调用元数据 */ },
  "timestamp": "ISO"
}
```
> 复现时按 `blocks` 顺序逐块还原；`think`/`tool` 默认折叠（只显示最新一行），`body` 展开，`clarify` 强制展开 —— 与当初一致。

#### 1.7.2 后端会话存储结构（本地文本文件，初期不用数据库）
每个会话为目录 `sessions/{id}/`：
- `meta.json`：标题、created_at、updated_at、pinned 等。
- `messages.jsonl`：用户/助手消息（含 `blocks[]`，逐行 JSON）。
- `corpus.json`：本会话文献语料。
- `review-latest.md` / `review-vN.md`：最新与版本化综述（v1, v2, v3…，每次重写递增，无字母后缀）。
- `matrix-latest.md`：文献矩阵（**仅在用户显式要求生成后才存在**）。
- `outline.json`：大纲。
- 并发安全：filelock，原子写（.tmp → 替换）。

#### 1.7.3 切换会话不中止当前任务（后台续跑 + 返回续渲染）
- 用户在生成进行中点击其它历史会话：**不得中止当前任务**。当前任务转入**后台**继续在服务端运行（SSE 连接可断开，任务不取消）。
- 切到的会话正常加载其历史；原会话的 taskId、已接收事件游标（`since`）记录在前端会话态（按 session 维护一份流状态）。
- **返回原会话时**：用 `GET /api/tasks/{taskId}/stream?since=N` **从断点续传**，继续渲染后续增量；若任务已在后台完成，则改为读取已落盘消息复现。
- 因此前端需按"会话 → 流状态/任务"维护多份独立流，互不打断；仅"停止"按钮显式取消当前可见任务。
- 任务状态可经 `GET /api/tasks/{id}/status` 查询（running/done/error）。

**相关任务接口：**
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tasks` | 创建并启动任务 |
| `GET` | `/api/tasks/{id}/stream?since=N` | SSE 流（支持断点续传，供返回续渲染） |
| `GET` | `/api/tasks/{id}/status` | 轮询任务状态 |
| `DELETE` | `/api/tasks/{id}` | 取消任务（仅"停止"按钮触发） |
| `GET` | `/api/sessions/{id}/review` | 获取最新综述 |
| `POST` | `/api/sessions/{id}/matrix` | **按需生成**文献矩阵（用户显式要求时） |
| `GET` | `/api/sessions/{id}/matrix` | 获取已生成矩阵（未生成则 404/空） |
| `GET` | `/api/sessions/{id}/library` | 本会话文献列表 |

### 1.8 Artifact 面板（右侧）

主 Tab：

| Tab | 内容 | 来源 | 可见性 |
|-----|------|------|--------|
| **大纲 Outline** | 大纲结构（主题、研究问题、子主题、章节结构） | artifact `literature-outline+json` | 有大纲时 |
| **综述 Review** | 最新综述 markdown，含版本下拉（latest / v1 / v2…）+ 导出按钮 | artifact `markdown`（delivery=artifact） | 有综述时 |
| **矩阵 Matrix** | 文献矩阵（论文 × 维度） | `POST /api/sessions/{id}/matrix` 生成的 markdown | **首轮不生成**；用户显式要求后才出现 |
| **文献 Literature** | 本会话收录文献（标题、作者、年份、摘要、DOI/URL、引用，可按子主题标签筛选，导出 APA） | `GET /api/sessions/{id}/library` | 有文献时 |

**矩阵按需生成（要求 5）：**
- 首轮综述**不主动生成矩阵**，矩阵 Tab 默认不出现或显示空态"尚未生成矩阵"。
- 用户在后续对话**显式要求**（如"生成文献矩阵"/"对比成矩阵"）时，调用 `POST /api/sessions/{id}/matrix` 生成并展示，落 `matrix-latest.md`。

**可见性与提示：**
- 存在综述产物即认为有 Artifact 面板。
- 面板存在但未打开时，给布局加"轻推"动画（约 4 秒脉冲），并由回合收尾行的"查看综述"内联链接引导打开。
- 流式中维持"钉住"的产物状态；流结束产物保持可见，不清空；切换会话时按目标会话重新加载（原会话产物随其流状态保留，返回可见）。

### 1.9 意图路由与计划确认

#### 1.9.1 意图类型（后端判定，精简为 3 类）
- `new_topic`：首轮（无语料），完整流水线（理解→检索→抓取→引用→综述）；**矩阵不在首轮生成**。
- `append_urls`：第 2 轮起含 URL/上传链接，**抓取用户 URL → 追加文献 → 基于扩充语料重写整篇综述**（不重新检索）。
- `query_corpus`：**其余一切情况的兜底**，LLM 依据已生成综述与语料回答问题（不生成综述，走聊天气泡）。

判定顺序：①首轮→new_topic；②第 2 轮起含 URL→append_urls；③其余→query_corpus。已删除 `subtopic_change`、`review_refine`、`short_answer` 分支。

详见 `docs/flow-card-logic-and-prompts.md`。

#### 1.9.2 计划确认门（plan_confirm）
当开启大纲模式且首轮 `plan_confirm=true`：
- 生成大纲后**在抓取前暂停**，发出 `literature_clarification`（kind=outline_confirm）。
- 显示澄清卡（type=clarify，强制展开），列出已生成子主题，提供：①确认继续；②选择其它推荐研究方向重生成。
- 用户下一条消息触发 `resume_mode=generate_only`（跳过检索）。
- 注：本门用于首轮 new_topic 的方向确认；不再支持会话中"增删/修改子主题"操作。

#### 1.9.3 澄清卡内容示例
```
等待澄清
─────────────────────────────
您的大纲已经生成：
 • 子主题 1: AI-native MOM
 • 子主题 2: 信任与安全
你可以：
 1. 确认继续撰写综述
 2. 选择其它推荐研究方向并重新生成
```

### 1.10 主会话异常与边界
| 场景 | 处理 | 体验 |
|------|------|------|
| SSE 超时挂起 | 看门狗 120s abort | 错误态 + 重试按钮 |
| 任务服务端错误 | `event:error` 带 message | Toast 错误详情 + 重试 |
| 用户点击停止 | 取消任务接口 | 清流、回 idle |
| 部分抓取失败 | SSE 继续，库内标失败 | 收尾行"42 成功 / 3 失败" |
| 检索零结果且无用户链接 | 澄清门 kind=search_zero | 澄清卡请用户扩展域名/关键词 |
| 流式中切换到其它会话 | **不中止**，当前任务转后台续跑 | 返回原会话时从断点续传续渲染（见 1.7.3） |
| 用户上滑阅读 | 暂停自动滚动，保留位置 | — |

---

## 2. 文献库（`/library`）

### 2.1 用途
集中管理综述会话中自动抽取/生成的全部引用：浏览、查看、筛选、编辑元数据，统一按 APA 格式化，并提供被引/他引等文献计量数据。

### 2.2 页面布局：两栏
- 头部：标题"文献库"；副标题"共 {count} 条文献"；操作按钮"刷新元数据"（并行从 Crossref/OpenAlex 拉取被引/参考文献，默认并行 4，范围 1–12）。
- 左栏（约 65%）：文献列表面板（含搜索/筛选）。
- 右栏（约 35%）：选中文献详情面板。

### 2.3 列表面板

#### 2.3.1 工具栏
1. **搜索框**：占位"搜索文献…"；大小写不敏感子串匹配，搜索范围 = 标题 + 作者 + URL + DOI + 出处 + 年份 + APA 引用文本 + display_index + 标签（拼成单串）。
2. **筛选芯片**（互斥单选）：
   - "全部"：不过滤。
   - "有全文"：`availability.has_full_text === true`。
   - "失败"：`fetch_status==='failed'` 或 `cite_status==='failed'`。
   - "收藏"：`starred === true`。
   - 可选"本会话"：当启用会话筛选且有激活会话时，按 provenance 中 session_id 过滤。
3. **密度切换**（可选）："舒适"（默认，卡片更松）/"紧凑"。
4. **标签过滤条**：列出全部标签及计数 `{标签} {count}`；多选 OR 逻辑；"清除标签"按钮；计数来自 `GET /library/tags`。
5. **结果计数**："{筛选数} / {总数} 条"。

排序：失败项优先，其后按 `display_index` 升序。

空状态提示："暂无收录文献。在综述会话中生成引用后会自动追加到此库。"

#### 2.3.2 文献卡片（LibraryRefCard）
卡片结构：
- **序号+标题**：`[{listIndex}] {title}`（标题缺失时由 URL 路径推导或"（标题待补全）"）。
- **作者行**：≤3 位全列；>3 位"作者1, 作者2 et al."；空显示"作者未知"。
- **出处/年份/计量**：`{venue} · {year} · 被引 {n} / 他引 {n}`。
- **标签**：最多显示 3 个，溢出显示"+n"。
- **右侧操作**：
  - "引用"按钮：复制 APA（按 listIndex 格式化后复制到剪贴板）。
  - 收藏按钮 ★/☆（切换 `starred`，调 `PATCH /library/items/{id}/star`）。
  - 删除按钮（确认弹窗："从文献库删除该条？仅移除库内记录，不影响已生成的综述文件。"）。
- **徽标行**（最多 3 个，按优先级）：抓取失败 / 引用失败 / 全文（点开全文 Tab）/ PDF / DOI（跳 doi.org）/ 原文（跳 url）/ "{n} 个综述"（点开综述 Tab）。
- 交互：点击卡片体选中并加载详情；键盘 Enter/Space 同效。

### 2.4 详情面板（LibraryDetailPane）

头部："[{index}] {标题}"。Tab 导航如下（部分按条件出现）：

1. **摘要**（始终）：书目区（标题/作者/出处/引证/DOI/出版社）+ 内联 DOI 编辑器 + 摘要正文。摘要优先取 `item.abstract`（>40 字且无 URL 视为有效），否则从全文抽取并标注"以下摘自抓取正文中的 Abstract 段落。"；无则"暂无摘要。"
2. **全文**（仅 `has_full_text`）：markdown 渲染（净化，最多 12 万字）；不可用时"全文尚未落盘或抓取失败。"
3. **元数据**（始终）：被引/他引（含"他引预览"前 10 条参考文献）、DOI 编辑器、URL、卷/期/页码、出版社、标签编辑器、收录综述列表、APA 引用文本。
4. **综述**（仅 provenance 非空）：列出引用了本条的会话（标题可点击跳转该会话、文中引用序号"文中引用 [3]"、会话首问）；来自 `GET /library/items/{id}/related-sessions`，失败回退本地 provenance。
5. **PDF**（仅 `has_pdf` 且 full_text.path 含 `pdfs/`）：iframe 内嵌 `/api/library/pdfs/{filename}`。

**DOI 内联编辑器**：输入框（占位 `10.xxxx/xxxxx`）+ "保存" + "从 Crossref 刷新"（无 DOI 时禁用）；保存调 `PATCH /library/items/{id}/metadata`（`refresh_crossref:true`），自动查询被引与他引。

**标签编辑器**：当前标签 chip（带 × 移除）+ 输入框（"添加标签，回车确认"）+ 其它标签建议；每条最多 20 个标签，每个最多 48 字符，大小写不敏感去重；调 `PATCH /library/items/{id}/tags`。

### 2.5 数据模型（LibraryItem）
```typescript
type LibraryItem = {
  id: string;                 // UUID hex（16 位）
  display_index: number;      // 顺序编号 [1,2,3…]，对应引用序号
  canonical_key?: string;     // 由 DOI 或 URL 推导，用于去重
  title: string;
  authors: string[];
  venue?: string; year?: string; month?: string;
  volume?: string; issue?: string; pages?: string;
  url: string; doi?: string; publisher?: string;
  abstract?: string;          // 最多 2000 字
  summary_bullets?: string[];
  full_text?: { kind: "markdown"|"pdf"; path: string; char_count?: number; fetched_at?: string } | null;
  citation_count?: number | null;       // 被引
  references_count?: number | null;     // 他引（参考文献条数）
  references_preview?: Array<{ title?: string; year?: string; doi?: string }>; // 最多 30
  availability: {
    has_abstract?: boolean; has_full_text?: boolean; has_pdf?: boolean;
    fetch_status?: "ok"|"failed"|"blocked"|"pending";
    cite_status?: "ok"|"failed"|"partial"|"pending";
  };
  citations?: Record<string,string>;    // {"apa": "..."}（含 [n] 占位；仅 APA）
  provenance?: Array<{ session_id: string; role: string; turn_at?: string; session_title?: string; review_ref_index?: number }>;
  tags?: string[];            // 最多 20
  subtopic_tags?: string[];
  starred?: boolean;
  enrich_lite?: { method_one_liner?: string; findings_one_liner?: string; year?: string };
  created_at?: string; updated_at?: string;
};
```

### 2.6 存储格式（参考实现）
- 主库文件 `{DATA_DIR}/refs/library.json`（JSON，FileLock 并发安全）：
```json
{
  "version": 1,
  "next_display_index": 127,
  "items": { "id1": {/*LibraryItem*/}, "id2": {/*…*/} },
  "keys": { "canonical_key1": "id1" }
}
```
- 全文单独落盘 `{DATA_DIR}/sources/{item_id}.md`；PDF 在 `{DATA_DIR}/pdfs/{filename}`。
- 兼容导出：`ref-list.txt`（全部引用文本，库变更时自动同步）、`index.json`（旧格式索引）。

### 2.7 引用抽取与格式化

#### 2.7.1 引用格式（仅 APA）
- **APA**：`[1] A. Author (2020). Deep Learning. Nature. https://doi.org/10.1038/x`

引用文本以 `[n]` 占位存储于 `item.citations.apa`，渲染/复制时用真实列表序号替换。已移除 ACM 格式与个人切换项。

#### 2.7.2 抽取流水线
1. **出版商识别**：从域名识别 arxiv / dblp / acm / ieee / semantic_scholar / elsevier / researchgate / google_scholar / 通用；其中 elsevier、researchgate、google_scholar 为**屏蔽源**（直接报错）。
2. **元数据层合并**：出版商 API（arXiv Atom、Semantic Scholar API）+ HTML 引用 meta（Highwire/Google Scholar）+ 正文抽取（标题/作者/年份/DOI/摘要）。
3. **成功判定**：有效标题（>8 字、无导航关键词、非纯哈希）+ 作者或年份至少其一 + 学术信号（有 DOI / 可信出版商 / arXiv URL）。
4. **富化**：OpenAlex（DOI 或按标题/作者/年份反查）+ Crossref（被引、参考文献、补全元数据）。
5. **入库**：按 canonical key（DOI 优先，否则 URL）去重 upsert；分配 display_index；生成 APA 引用；写 provenance（session_id、role、时间戳）；同步兼容导出。
6. **元数据不足不写半条**：正文中标注"待核实"。

### 2.8 文献库接口
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/library/items` | 列出全部（按 display_index） |
| `GET` | `/library/items/{id}` | 单条 + full_text |
| `GET` | `/library/tags` | 标签及计数 |
| `GET` | `/library/items/{id}/related-sessions` | 相关综述会话 |
| `PATCH` | `/library/items/{id}/star` | `{starred}` |
| `PATCH` | `/library/items/{id}/tags` | `{tags[]}` |
| `PATCH` | `/library/items/{id}/metadata` | 编辑书目（可 `refresh_crossref`） |
| `DELETE` | `/library/items/{id}` | 删除（连带源文件） |
| `DELETE` | `/library/items` | 清空 |
| `POST` | `/library/items/{id}/enrich` | 按 DOI 富化 |
| `POST` | `/library/refresh-metadata` | 批量并行刷新（`{item_ids?, parallel:1-12}`） |
| `POST` | `/library/reconcile` | 从会话/产物补抽引用（`{session_id?, mode:"session"|"all"|"failed_only"}`） |
| `GET` | `/library/pdfs/{filename}` | 提供 PDF（校验路径在 pdfs/ 下） |

### 2.9 边界与异常
- 缺标题/作者/出处/摘要分别有占位文案（见 2.3.2 / 2.4）。
- 失败项以红色"抓取失败/引用失败"徽标显示，可经"刷新元数据"或 `/enrich` 重试。
- 并发写用 FileLock；前端列表可缓存（约 30s）但允许强制刷新。
- 去重合并：更新 display_index、合并 provenance（上限约 20 条），重复计入 merged 计数。

---

## 3. 设置 — 个人偏好（`/settings/personal`）

- 路由：`/settings/personal`；`/settings` 默认重定向至此。
- **引用格式固定为 APA**，不再提供 APA/ACM 切换项（原 `citation_format` 偏好已移除）。
- 该页面现无可配置字段；可保留为占位说明页，或在导航中隐去。
- 如保留接口，`GET /api/settings/personal/preferences` 恒返回 `{ citation_format: "apa" }`（只读）。

---

## 4. 设置 — 管理员（`/settings/admin/*`）

### 4.1 配置体系与优先级
- **系统设置（管理员）**：凭据 / 实例 / 能力 / Prompts / 存储，落盘 `/config/system.*.json`。
- **个人设置**：引用格式已固定 APA，无可切换项（如保留 `/config/personal.preferences.json` 仅为只读占位）。
- **优先级**：系统配置 > `.env` 环境变量 > `deploy.defaults.json`。秘钥若系统配置缺省则回退 `.env`（TAVILY_API_KEY、JINA_API_KEY、OPENAI_API_KEY 等）。
- 运行时把系统+个人+env 合并为单一扁平 dict 传给 agents。
- 旧版 `agent.json` 首次运行迁移到 v2（幂等）。
- 所有 JSON 保存用**原子写**（写 .tmp → FileLock → 替换），防崩溃半写。

### 4.2 导航（管理员侧栏）
| 分组 | 项 | 路由 |
|------|----|------|
| System | 概览 | `/settings/admin` |
| System | 存储 | `/settings/admin/storage` |
| Connect | 凭据 | `/settings/admin/credentials` |
| Connect | 实例库 | `/settings/admin/instances` |
| Capability | 检索与抓取 | `/settings/admin/capabilities` |
| Capability | 编排与综述 | `/settings/admin/prompts` |

### 4.3 概览页（`/settings/admin`）
落地页展示系统就绪度：
- **存储行**：标签"持久化存储"；状态徽标"已通过/待配置"；后端标签（Turso（云端 SQLite）/ Hybrid / 本地文件）；链接到存储页。
- **能力行**（5 个）：`review_main` 综述主模型、`orchestrator` 编排模型、`web_search` 网络检索、`web_fetch` 网页抓取、`literature_source` 文献来源。
  - 状态："已通过"= `ok && enabled && (引用已解析 或 无需引用)`；否则"待配置"。
  - 取值：能力引用 + 参数摘要，如 `deepseek-v4-pro · search_max_results=20 · search_retry_count=3`。
- 接口：`GET /api/settings/system/overview` → `{ capabilities[], credentials[], instances[], storage }`。

### 4.4 凭据页（`/settings/admin/credentials`）

#### 4.4.1 凭据类型
| type | 用途 | 字段 |
|------|------|------|
| `tavily` | 网络检索（需 Key） | secret |
| `brave` | 网络检索（需 Key） | secret |
| `semantic_scholar` | 可选，增强 multi_academic | secret |
| `jina` | 网页抓取/Markdown（需 Key） | secret |
| `llm:openai` | OpenAI 兼容 LLM | secret, base_url, group_id |
| `llm:minimax` | MiniMax | secret, base_url, group_id |
| `llm:alibaba` | 阿里 Qwen | secret, base_url, group_id |
| `llm:zhipu` | GLM | secret, base_url, group_id |
| `llm:ollama` | 本地 Ollama（无需 secret） | secret(可空), base_url, group_id |

#### 4.4.2 每行结构
- 头部工具条：可编辑名称 + 状态徽标（未测试/已通过/失败）+ "最近测试：{时间}" + 行内反馈 + "测试" + "保存"。
- 字段：
  - **API Key**（password，`cred-key-{id}`）：已存在时显示掩码，聚焦转可编辑，失焦留空回退掩码；占位"点击输入新 Key"/"填写 Key"。
  - **Base URL**（仅 LLM，`cred-url-{id}`）：占位"LLM 接口地址"，如 `https://api.deepseek.com/v1`。
  - **Group ID**（仅 LLM，MiniMax 专用，`cred-gid-{id}`）：占位"可选"。

#### 4.4.3 测试行为
- `POST /api/settings/system/credentials/{id}/test`（可带 `{query?}`，默认 "transformer attention paper arxiv"）。
- Tavily/Brave：真实检索返回命中数；401 → "Key 无效、已撤销或已过期"；成功更新状态=ok 并记时间戳。
- Semantic Scholar：查询 min_year=2017，处理 429 限流。
- 通用 LLM：基础检查（secret 存在）。Ollama：无需 secret。Jina：尽力而为（有 secret 视为 ok）。

#### 4.4.4 持久化
- `POST /credentials` 建；`PUT /credentials/{id}` 改（`{secret?, base_url?, group_id?}`，secret 设空=清除→状态 unknown，改 secret 时 `last_verified_at=null`）；`DELETE /credentials/{id}`（被实例引用则拒绝）。
- 文件 `system.credentials.json`：每项含 id/type/name/secret/base_url/group_id/status/last_verified_at/created_at/updated_at。
- **掩码**：API 永不返回明文，前端只收 `has_secret` + `masked_secret`（末 4 位）。

### 4.5 实例库页（`/settings/admin/instances`）
定义 LLM 实例 = 名称 + 模型名 + 绑定的 LLM 凭据。
- 头部"新增实例"按钮 → 创建面板：名称（占位 review-main）、凭据（仅 `llm:` 类）、模型（占位"如 gpt-4o, deepseek-chat"）；"创建"（无凭据禁用）。
- 实例行：名称、凭据下拉（显示 `{name} · {掩码或未配置}`）、模型（等宽）；头部含状态徽标 + 测试 + 保存。
- 测试：`POST /instances/{id}/test` 仅做绑定校验（凭据存在 + 有 secret（Ollama 除外）+ 模型非空）→ "已通过基础检查"。
- 持久化 `system.instances.json`：id/name/provider（由凭据 type 推导）/credential_id/model_name/default_params/status/时间戳。
- `DELETE` 被能力引用则拒绝。

### 4.6 能力页 — 检索与抓取（`/settings/admin/capabilities`）

底部含 **Web 后端连通测试面板**。

#### 4.6.1 web_search 卡片
| 字段 | key | 类型/选项 | 默认 | 约束 |
|------|-----|-----------|------|------|
| 检索后端 | search_provider | tavily / brave / multi_academic / openalex / native | multi_academic | tavily/brave 无对应凭据时禁用 |
| 检索条数 | search_max_results | 数字 | 20 | 1–80 |
| 失败重试 | search_retry_count | 数字 | 3 | 0–3 |
| 检索深度 | search_depth | basic / advanced（仅 tavily） | advanced | — |
| 包含域名 | include_domains | 文本域（每行一个，按 `[\n,]+` 拆） | 学术域名列表 | 白名单 |
| 排除域名 | exclude_domains | 文本域 | — | 命中即剔除 |
| 强制域名白名单过滤 | enforce_domain_filter | 勾选 | true | 关闭仅检索不硬过滤 |
| 启用 junk 过滤 | enable_junk_filter | 勾选 | true | 过滤非论文页 |

provider 为 tavily/brave 时显示**凭据绑定**下拉（`web_search-ref`，按类型过滤）；其它显示"无需 API Key"。

选项文案：
- tavily："Tavily（需 API Key，通用）"
- brave："Brave Search（需 API Key，通用）"
- multi_academic："multi_academic（arXiv+CrossRef+PMC+OpenAlex+SS，无需 Key）"
- openalex："OpenAlex（学术，无需 Key）"
- native："native（DDG HTML，无需 Key）"

#### 4.6.2 web_fetch 卡片
| 字段 | key | 类型/选项 | 默认 | 约束 |
|------|-----|-----------|------|------|
| 抓取后端 | fetch_provider | jina / native | native | jina 无凭据时禁用 |
| PDF 解析 | pdf_extract_backend | pypdf / pymupdf4llm（仅 native） | pymupdf4llm | 选 pymupdf4llm 时提示 Artifex 商用许可 |
| 抓取篇数 | max_fetch_urls | 数字 | 5 | 1–50 |
| 并行 | fetch_parallel | 数字 | 3 | 1–8 |
| 超时(秒) | fetch_timeout_sec | 数字 | 45 | 10–120 |
| 重试 | fetch_retry_count | 数字 | 0 | 0–3 |
| 单篇上限(字) | max_source_chars | 数字 | 14000 | 2000–50000 |

provider 为 jina 时显示凭据绑定（`web_fetch-ref`，类型 jina）。

#### 4.6.3 Web 后端连通测试面板
- 提示当前 fetch/search 后端；改后端须先在能力页保存。
- 抓取测试：URL 输入（默认某 webmedia 文章）→ "测试 web_fetch" → 显示 `{provider} · 原始 N 字节 · 正文 N 字 [· PDF][· title][· 超时上限 Ns]` + 前 1200 字预览；正文 ≥80 字算通过。
- 检索测试：query 输入（默认 "systematic literature review methods"）→ "测试 web_search" → 显示 `{provider} · 命中 N 条` + 前 3 条结果；命中>0 算通过。

#### 4.6.4 持久化
- `PUT /api/settings/system/capabilities/{capability_id}`，body `{ primary_ref?, params? }`；`primary_ref = {kind:"credential"|"instance", id}`。
- 文件 `system.capabilities.json`：items[] 每项含 capability_id / label / enabled / primary_ref / params / 时间戳。

### 4.7 能力页 — 编排与综述（Prompts，`/settings/admin/prompts`）
编辑各阶段系统提示模板、绑定 LLM 实例、控制各阶段最大输出 token。

- 顶部全局保存条（仅 dirty 时显示）："有未保存的修改" + 全局"保存"。
- 按阶段分组：
  1. 意图理解与编排（orchestrate）：router、orchestrator、assessor。
  2. 搜索文献（search）：search_query_refiner。
  3. 获取文献（fetch）：pipeline。
  4. 创建综述（generate）：review_system_prompt_template。
- 每个 Prompt 含：
  - 标签 `{label}（{key}）` + 提示。
  - **最大输出 Token**（`tok-{key}`，范围 [80, max_tokens_limit]，占位 default_max_tokens）。
  - **模型实例选择**（`inst-{key}`，下拉显示 `{name} · {provider} · {model}`，参数键 `{group}_instance_id`）。
  - **模板编辑器**（`prompt-{key}`，等宽 textarea，review 模板 14 行其余 8 行，含 `{fmt_label}` 占位）；下方提示"最多 {max_len} 字符 · 当前 N · [已自定义|内置默认]"。
- 默认与元数据：`GET /api/settings/system/prompts/defaults` → `{ defaults:{key:模板}, meta:[{key,label,group,hint,max_len,default_max_tokens,max_tokens_limit}] }`。
- 持久化：
  - 单条保存（含模板 + 其 max_tokens + 组实例绑定）。
  - 全局保存：`PUT /capabilities/prompts`（全量 params）+ `PUT /capabilities/orchestrator`、`PUT /capabilities/review_main`（primary_ref）。
  - 落 `system.capabilities.json` 的 prompts 能力 params（模板空串=用内置默认；各 `*_instance_id` 空=回退 review_main/orchestrator）。
- 默认值参考：review_system_prompt_max_tokens=3000（上限 8000）；search_query_refiner_max_tokens=200（上限 500）。

### 4.8 存储页（`/settings/admin/storage`）
> **初期不启用数据库**：本页（Turso/云端 SQLite）为**后续可选项**，初期可在导航中隐藏或置灰，默认走本地文本文件存储。以下为后续启用时的规格。

配置 Turso（云端 SQLite）做会话/语料持久化。
- 头部：标题"持久化存储" + 状态徽标 + 后端标签 + 租户（非 default 时显示"租户 {tenant_id}"）+ 仅 dirty 启用保存。
- 部署说明（折叠）：冷启动依赖 env：`LITPILOT_STORAGE_BACKEND`、`TURSO_DATABASE_URL`、`TURSO_AUTH_TOKEN`；下方可保存运行期覆盖（即时生效）。
- 字段：
  - **数据库 URL**（`turso-url`，占位 `libsql://your-db.turso.io`，须以 `libsql://`/`https://`/`http://` 开头）。
  - **Auth Token**（`turso-token`，password，掩码+聚焦编辑，留空=不修改）。
  - **配置来源**（只读双徽标）：URL/Token 各显示来源"环境变量/管理员配置/未配置"。
- 持久化：`PUT /api/settings/system/storage`（`{database_url?, auth_token?}`，token 空串=移除）；文件 `system.storage.json`；公开响应不返明文，只给 `has_auth_token`/`masked_auth_token`/各来源/`turso_ready`/`backend`。

### 4.9 共享 UI 组件与状态
- InlineField（标签+控件+提示）、InlineCheck（勾选）、FieldTip（问号 tooltip）、SettingToolbar（标题|状态|反馈|操作）、SettingsListPanel。
- 状态徽标类：ok=绿、fail=红、pending/unknown=灰。
- 离开守卫：dirty 时离页提醒，防误丢编辑。

### 4.10 设置接口汇总
| 方法 | 端点 |
|------|------|
| GET/PUT | `/api/settings/personal/preferences` |
| GET | `/api/settings/system/overview` |
| GET/PUT | `/api/settings/system/storage` |
| GET/POST | `/api/settings/system/credentials` |
| GET/PUT/DELETE | `/api/settings/system/credentials/{id}` |
| POST | `/api/settings/system/credentials/{id}/test` |
| GET/POST | `/api/settings/system/instances` |
| GET/PUT/DELETE | `/api/settings/system/instances/{id}` |
| POST | `/api/settings/system/instances/{id}/test` |
| GET | `/api/settings/system/capabilities` |
| PUT | `/api/settings/system/capabilities/{id}` |
| POST | `/api/settings/system/capabilities/web_fetch/test` |
| POST | `/api/settings/system/capabilities/web_search/test` |
| GET | `/api/settings/system/prompts/defaults` |

### 4.11 配置文件清单
| 文件 | 范围 |
|------|------|
| `system.credentials.json` | API 密钥（响应掩码） |
| `system.instances.json` | LLM 实例绑定 |
| `system.capabilities.json` | 能力参数 + 引用 + Prompts |
| `system.storage.json` | Turso 连接 |
| `personal.preferences.json` | 个人偏好（引用格式已固定 APA，只读占位） |
| `deploy.defaults.json` | 部署默认（非敏感） |

---

## 5. 文献综述工作流（后端引擎规范）

```
理解问题 → web_search → web_fetch → 引用抽取 → LLM 综述 → 交付 Artifact
```
- 材料分栏喂给 LLM：`[web_search]` 摘要、`[网页材料]` 正文、`[Citations]` 已收录引用。
- 单 URL 抓取失败回退检索 snippet，不阻断整轮。
- 引用元数据不足不写半条记录，正文标注"待核实"。
- 多子主题（multi-aspect brief）：按子主题并行检索，可开 outline_mode + plan_confirm 在生成前确认大纲。
- 检索后端可选：tavily / brave / multi_academic / openalex / native；抓取后端：jina / native（native 支持 PDF 解析 pypdf / pymupdf4llm）。
- LLM 提供商：openai / zhipu / alibaba / minimax_intl / minimax_cn / ollama。
- **意图精简为 3 类**：new_topic（首轮完整流水线）、append_urls（第 2 轮起追加 URL 并基于扩充语料重写综述）、query_corpus（其余兜底，依据已生成综述回答）。引用格式固定 APA。流程与提示词详见 `docs/flow-card-logic-and-prompts.md`。

---

## 6. 非功能性需求
- **初期无数据库**：**强制使用本地文本文件**（JSON/JSONL/Markdown）+ FileLock 运行；Turso/SQLite 为后续可选项，初期管理员存储页可隐藏或置灰（见 4.8）。
- **UI 底座**：MESO `@meso.ai/ui` **2.1.1**（npm）+ `@meso.ai/types` 2.1.x；前端 **TypeScript 为主**（Next.js 15 / React 19）。
- **品牌资源**：统一取自 `brand/` 资源包，禁止自造 logo。
- **会话框非卡片**：除执行状态/统计原位更新外，文本一律流式追加；三类内容块（正文/思考/工具输出）独立风格，思考与工具输出默认折叠只显最新一行；澄清卡为唯一强制展开卡片。
- **历史一致复现**：从 `messages.jsonl` 的 `blocks[]` 还原，内容与样式（折叠态、统计、澄清卡）与当初一致。
- **任务后台续跑**：切换会话不中止生成，按会话维护独立流，返回时断点续传续渲染。
- **并发安全**：所有共享文件写入加锁、原子替换。
- **流式优先**：综述/进度必须真流式（SSE 透传，避免代理缓冲；前端 rAF 批渲染 + 120s 看门狗）。
- **秘钥安全**：API 返回一律掩码，明文只存服务端配置文件 / env。
- **成本可见**：检索/抓取/LLM 均可能产生第三方费用，UI 不隐藏并行度等放大成本的设置。
- **国际化**：界面文案中文为主（可扩展）；引用格式固定 APA。

---

## 7. 复制开发验收清单（节选）
- [ ] MESO `@meso.ai/ui` 2.1.1 底座 + 前端 TypeScript 为主；品牌资源全部取自 `brand/`。
- [ ] 初期无数据库，会话/语料/综述均落本地文本文件（JSONL/MD）+ filelock 原子写。
- [ ] 四列布局、响应式宽度、Artifact 开合收窄主区。
- [ ] 会话 CRUD + 置顶 + 本地激活会话恢复。
- [ ] 会话框**非卡片**：三类内容块（正文/思考/工具输出）独立风格统一；思考与工具输出默认折叠只显最新一行、点击展开；执行状态原位更新；文本流式追加。
- [ ] **澄清卡**独立设计、强制展开（唯一卡片例外）。
- [ ] 历史消息按 `blocks[]` 复现，内容与样式与当初一致。
- [ ] 切换会话**不中止**当前任务，后台续跑；返回原会话断点续传续渲染。
- [ ] Composer：多行输入、回车发送、链接上传（首轮禁用、第 2 轮起启用）、停止、静默提示、并行度芯片。
- [ ] 意图路由 3 类（new_topic / append_urls / query_corpus）+ 计划确认门 + 澄清卡；流程逻辑以 `docs/flow-card-logic-and-prompts.md` 为准。
- [ ] append_urls：追加文献后基于扩充语料重写整篇综述（v(n+1)）。
- [ ] **矩阵首轮不生成**，仅按用户显式要求经 `POST /api/sessions/{id}/matrix` 生成。
- [ ] Artifact Tab（大纲/综述/文献 + 按需矩阵）+ 综述版本下拉 + 导出。
- [ ] 文献库两栏 + 搜索/筛选/标签 + 卡片徽标 + 详情五 Tab + DOI/标签编辑 + 刷新元数据 + 引用复制（APA）。
- [ ] 引用抽取流水线（出版商识别、屏蔽源、成功判定、Crossref/OpenAlex 富化、去重 upsert、provenance）；引用格式固定 APA。
- [ ] 管理员各页（概览/凭据/实例/能力/Prompts/存储*）+ 掩码 + 测试 + 优先级合并（*存储页初期可隐藏；个人设置无引用格式切换）。
- [ ] 统一响应结构、原子写、FileLock、看门狗、掩码安全。

---

*本说明书基于 LitPilot 现有实现编写，目标是行为等价复制。像素值、文案、文件路径为参考实现取值，复制方可在保持交互契约一致的前提下调整。*
