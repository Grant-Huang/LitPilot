# LitPilot 功能需求说明书（复制开发版）

> 本文档面向**第三方开发团队**，目标是据此**从零复制开发一个功能等价的应用**。文档以"做什么、给用户看什么、交互如何、数据如何流动、如何持久化、异常如何处理"为主线，尽量给出具体的字段名、状态名、默认值、约束与端点契约。实现技术栈不作强制（参考实现为 Next.js + FastAPI + 本地文件 / Turso 存储），但**行为契约必须一致**。

---

## 0. 产品概述

### 0.1 定位
LitPilot 是一款面向科研人员的**文献综述助手**。用户用自然语言描述研究主题，系统自动完成：理解问题 → 学术检索 → 全文抓取 → 引用抽取 → 大模型综述生成 → 交付结构化产物（综述、文献矩阵、大纲），并把抽取到的引用沉淀进**文献库**。整个执行过程以"流程卡片"的形式实时可视化。

### 0.2 三大界面
| 界面 | 路由 | 职责 |
|------|------|------|
| 主会话窗口 | `/chat` | 文献综述对话、流程可视化、流式输出、右侧 Artifact 面板 |
| 文献库 | `/library` | 引用索引浏览、元数据编辑、按状态/标签筛选、引用复制导出 |
| 设置 - 个人 | `/settings/personal` | 个人偏好（引用格式） |
| 设置 - 管理员 | `/settings/admin/*` | 凭据、实例、能力（检索/抓取）、Prompts、存储 |

### 0.3 顶层数据流（一次综述）
```
用户输入主题
  → 创建 Task（POST /api/tasks）
  → SSE 流式执行：理解 → 检索 → 抓取 → 引用抽取 → 综述生成
  → 流程卡片实时更新（左/中）
  → 产物落到 Artifact 面板（右）：综述 / 矩阵 / 大纲
  → 引用 upsert 进文献库
  → 会话与消息落盘持久化
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

### 1.3 消息区与对话历史

#### 1.3.1 空状态（欢迎屏）
当无任何消息且未在流式时显示欢迎屏：
- LitPilot 品牌标识。
- 引导语："描述研究主题，左侧显示执行过程，综述与矩阵在右侧 Artifact 面板查看。"
- 对齐方式可配置：居中或置顶。

#### 1.3.2 历史消息渲染规则
逐条遍历历史消息：
- **用户消息**：普通气泡（ChatBubble，role=user，纯文本）。
- **助手消息（含执行轨迹）**：当消息 `extras.executionTrace` 或 `extras.turnWorkflow` 存在时，渲染"助手回合"（流程卡片 + 可选文字气泡）。
- **助手纯文本**：普通气泡。

**是否显示助手文字气泡的判定：**
- 仅当 `delivery === "chat"`（语料问答类意图）**且**消息正文非空**且** `artifactKind !== "review"`（综述类不在气泡里重复展示全文）时显示。
- `delivery === "process"`（流程叙述型）、空正文、或主产物即综述时，不显示气泡。

#### 1.3.3 实时回合（流式中）
当流式状态非 idle 时，在历史之后追加"实时回合"：
- 显示**运行中的流程卡片** + 增量文字（聊天/流程文本）。
- 含运行指示器（spinner / 进度）。

#### 1.3.4 自动滚动
- "贴底阈值" = 80px：`scrollHeight - scrollTop - clientHeight ≤ 80px` 视为用户在底部。
- 用户在底部时：新用户消息自动贴底；流式中随增量平滑滚动。
- 用户上滑阅读历史时：**不强制跳动**，保留阅读位置。
- 切换会话（reset key 变化）时：重新贴底。
- 用 ResizeObserver 监听容器尺寸变化（如 Artifact 面板开合导致主区宽变化）。
- 不在底部时显示"回到底部"悬浮按钮（FAB）。

### 1.4 流程卡片与执行可视化（核心差异化功能）

整个执行过程拆成若干**流程卡片**（WorkflowCard），每张卡片可折叠，含若干**日志行**（步骤）。

#### 1.4.1 卡片类型与标题
| 卡片类型 | 标题 |
|----------|------|
| `understand` | 理解研究问题 |
| `brief` | 研究计划 |
| `search` | 文献检索 |
| `fetch` | 抓取全文 |
| `cite` | 引用抽取 |
| `attributes` | 文献结构化 |
| `outline` | 大纲规划 |
| `generate` | 综述生成 |
| `matrix` | 文献矩阵 |
| `revise` | 章节修订 |
| `corpus_qa` | 语料问答 |
| `clarify` | 等待澄清 |
| `manage` | 文献库操作 |

#### 1.4.2 卡片状态与视觉
- 状态：`pending | running | done | error`。
- 状态图标：pending=空心圈 ○；running=旋转 loader ⟳；done=对勾 ✓；error=叉/警告 ⚠。
- 卡片**默认展开**条件：state===running，或澄清卡（type==='clarify'）强制展开。
- 卡片头部含状态标记 + 标题；展开后体内为日志行列表。
- 完成后给出**摘要文字**（state≠pending 时），例如："文献检索 · 检索 3 pass · 纳入 47 篇 · 21s"。

#### 1.4.3 日志行（步骤）
每个步骤一行：状态图标 + 主文本 + 可选"结果"后缀 + 可选展开详情。
- 步骤类型：`tool | inline | think`。
- 有详情时主文本变为可点击的展开/折叠按钮（chevron ▸/▾），展开后用 `<pre>` 显示详情。

示例日志行：
```
✓ 文献检索 3/5 PASS（by_source 并行）· 检索到 142 篇 · 24s
  → 逻辑检索 · arXiv（21 篇）
  → 混合检索 · OpenAlex（48 篇）
⚙ 抓取 43/150 · 已获取 12 篇，4 篇超时，27 篇待入队
✓ 引用抽取 · 12 篇完成 · APA/ACM 格式化 · 3s
○ 综述生成 · 逐章流式生成…（进行中）
```

#### 1.4.4 检索进度树（SearchProgressView）
当多子主题（multi-aspect brief）且开启大纲模式、检索阶段产生 `literature_subtopic_*` 事件时，在检索卡内渲染层级树：
```
子主题规划（1/3 完成）
├─ 子主题 1: AI-native MOM 架构
│  └─ 检索中（2/5 pass）
│     ├─ OpenAlex (12 篇) [done]
│     └─ arXiv (进行中…)
└─ 子主题 2: 信任与安全
   └─ 检索完成（5/5 pass）
      ├─ OpenAlex (18 篇)
      ├─ Semantic Scholar (7 篇)
      └─ Web Search (失败)
```
节点层级：子主题块 → 数据源行（显示命中数或失败徽标 + 状态图标）→ 过滤明细行（LLM 二段过滤完成后显示保留/剔除数）。

#### 1.4.5 回合完成栏（TurnCompletionBar）
流式结束后追加一条汇总栏：
- **标题行**：聚合各阶段统计，如"检索 · 纳入 47 篇 · 获取 42 篇 · 综述已生成"。
- **简评行**（非流式时）：弱子主题提示，如"子主题『信任机制』文献较少，仅 3 篇，建议扩展搜索"。
- **CTA**：当存在综述/矩阵产物但 Artifact 面板未打开时显示"综述已生成 [查看综述]"按钮，点击打开右侧面板。

### 1.5 输入器（Composer）

底部输入区结构：URL/并行度元信息行 + 多行文本框 + 控制条（上传 / 活动提示 / 发送或停止）。

#### 1.5.1 文本输入
- 多行自适应文本框，最少 2 行，最多 6 行。
- 占位符："描述你的研究主题或综述问题…"。
- 回车发送；Shift+回车换行。
- 流式进行中禁用输入。

#### 1.5.2 链接上传
- "+"附件按钮，接受 `.txt/.csv/.json`，从中解析 http(s) 链接。
- **首轮禁用上传**（new_topic，须先用文字描述主题）；首条助手回复后开启（append_urls 多轮可追加链接）。
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

### 1.7 任务与会话消息持久化

#### 1.7.1 发送→执行→落盘流程
1. 用户发送 → `POST /api/tasks`（body: `{session_id, message, fetch_urls}`）→ 得 taskId。
2. 连接流 `GET /api/tasks/{taskId}/stream?since=0`。
3. 累积 SSE 事件构建 `executionTrace` / `turnWorkflow`。
4. 流结束（done）→ 物化为助手消息 `LitPilotMessage`（含 extras）。
5. 持久化：`POST /api/sessions/{id}/messages`（用户消息与助手消息分别落盘）。
6. 回读校验：`reloadSessionMessages(sessionId, {pendingUserText, maxAttempts:5})` 轮询直至消息出现或超时；回读失败时回退展示已物化的实时消息。

#### 1.7.2 后端会话存储结构（参考实现）
每个会话为目录 `sessions/{id}/`：
- `meta.json`：标题、created_at、updated_at、pinned 等。
- `messages.jsonl`：用户/助手消息（extras 序列化为 JSON）。
- `corpus.json`：本会话文献语料。
- `review-latest.md` / `review-vN.md`：最新与版本化综述（v1, v1a, v1b, v2…）。
- `matrix-latest.md`：最新文献矩阵。
- `outline.json`：大纲（多子主题时）。

**相关任务接口：**
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tasks` | 创建并启动任务 |
| `GET` | `/api/tasks/{id}/stream?since=N` | SSE 流（支持续传） |
| `GET` | `/api/tasks/{id}/status` | 轮询任务状态 |
| `DELETE` | `/api/tasks/{id}` | 取消任务 |
| `GET` | `/api/sessions/{id}/review` | 获取最新综述 |
| `GET` | `/api/sessions/{id}/matrix` | 获取矩阵 |
| `GET` | `/api/sessions/{id}/library` | 本会话文献列表 |

### 1.8 Artifact 面板（右侧）

四个主 Tab：

| Tab | 内容 | 来源 |
|-----|------|------|
| **大纲 Outline** | 多子主题大纲结构（主题、研究问题、子主题、章节结构） | artifact `literature-outline+json` |
| **综述 Review** | 最新综述 markdown，含版本下拉（latest / v1 / v1a…）+ 导出按钮 | artifact `markdown`（delivery=artifact） |
| **矩阵 Matrix** | 文献矩阵（论文 × 属性：问题/方法/发现） | artifact `literature-matrix+markdown` |
| **文献 Literature** | 本会话收录文献（标题、作者、年份、摘要、DOI/URL、引用，可按子主题标签筛选，可导出 APA/ACM） | 后端 `GET /api/sessions/{id}/library` |

**可见性与提示：**
- 存在综述产物即认为有 Artifact 面板。
- 面板存在但未打开时，给布局加"轻推"动画（约 4 秒脉冲），并由回合完成栏 CTA 引导打开。
- 流式中维持"钉住"的产物状态；流结束产物保持可见，不清空；切换会话时重置并从会话重新加载。

### 1.9 意图路由与计划确认

#### 1.9.1 意图类型（后端判定）
- `new_topic`：首轮，完整流水线。
- `subtopic_change`：用户显式修改子主题。
- `append_urls`：多轮追加链接（不重新检索）。
- `review_refine`：基于用户编辑重生成（不检索/抓取）。
- `query_corpus`：对已有语料提问（不生成综述，走聊天气泡）。
- `short_answer`：意图不明时的兜底。

#### 1.9.2 计划确认门（plan_confirm）
当开启大纲模式且首轮 `plan_confirm=true`：
- 生成大纲后**在抓取前暂停**，发出 `literature_clarification`（kind=outline_confirm）。
- 显示澄清卡（type=clarify，强制展开），列出已生成子主题，提供：①确认继续；②修改大纲重生成；③增删子主题。
- 用户下一条消息触发 `resume_mode=generate_only`（跳过检索）。

#### 1.9.3 澄清卡内容示例
```
等待澄清
─────────────────────────────
您的大纲已经生成：
 • 子主题 1: AI-native MOM
 • 子主题 2: 信任与安全
你可以：
 1. 确认继续撰写综述
 2. 修改大纲并重新生成
 3. 添加/删除子主题
```

### 1.10 主会话异常与边界
| 场景 | 处理 | 体验 |
|------|------|------|
| SSE 超时挂起 | 看门狗 120s abort | 错误态 + 重试按钮 |
| 任务服务端错误 | `event:error` 带 message | Toast 错误详情 + 重试 |
| 用户点击停止 | 取消任务接口 | 清流、回 idle |
| 部分抓取失败 | SSE 继续，库内标失败 | 完成栏"42 成功 / 3 失败" |
| 检索零结果且无用户链接 | 澄清门 kind=search_zero | 卡片请用户扩展域名/关键词 |
| 流式中切换到其它会话 | 中止当前流、清实时消息、加载新会话 | — |
| 用户上滑阅读 | 暂停自动滚动，保留位置 | — |

---

## 2. 文献库（`/library`）

### 2.1 用途
集中管理综述会话中自动抽取/生成的全部引用：浏览、查看、筛选、编辑元数据，支持 APA/ACM 格式化，并提供被引/他引等文献计量数据。

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
  - "引用"下拉：复制 APA / 复制 ACM（按 listIndex 格式化后复制到剪贴板）。
  - 收藏按钮 ★/☆（切换 `starred`，调 `PATCH /library/items/{id}/star`）。
  - 删除按钮（确认弹窗："从文献库删除该条？仅移除库内记录，不影响已生成的综述文件。"）。
- **徽标行**（最多 3 个，按优先级）：抓取失败 / 引用失败 / 全文（点开全文 Tab）/ PDF / DOI（跳 doi.org）/ 原文（跳 url）/ "{n} 个综述"（点开综述 Tab）。
- 交互：点击卡片体选中并加载详情；键盘 Enter/Space 同效。

### 2.4 详情面板（LibraryDetailPane）

头部："[{index}] {标题}"。Tab 导航如下（部分按条件出现）：

1. **摘要**（始终）：书目区（标题/作者/出处/引证/DOI/出版社）+ 内联 DOI 编辑器 + 摘要正文。摘要优先取 `item.abstract`（>40 字且无 URL 视为有效），否则从全文抽取并标注"以下摘自抓取正文中的 Abstract 段落。"；无则"暂无摘要。"
2. **全文**（仅 `has_full_text`）：markdown 渲染（净化，最多 12 万字）；不可用时"全文尚未落盘或抓取失败。"
3. **元数据**（始终）：被引/他引（含"他引预览"前 10 条参考文献）、DOI 编辑器、URL、卷/期/页码、出版社、标签编辑器、收录综述列表、APA/ACM 引用文本。
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
  citations?: Record<string,string>;    // {"apa": "...", "acm": "..."}（含 [n] 占位）
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

#### 2.7.1 两种格式
- **APA**：`[1] A. Author (2020). Deep Learning. Nature. https://doi.org/10.1038/x`
- **ACM**：`[1] A. Author. 2020. Deep Learning. Nature. DOI:https://doi.org/10.1038/x`

引用文本以 `[n]` 占位存储于 `item.citations.apa/acm`，渲染/复制时用真实列表序号替换。

#### 2.7.2 抽取流水线
1. **出版商识别**：从域名识别 arxiv / dblp / acm / ieee / semantic_scholar / elsevier / researchgate / google_scholar / 通用；其中 elsevier、researchgate、google_scholar 为**屏蔽源**（直接报错）。
2. **元数据层合并**：出版商 API（arXiv Atom、Semantic Scholar API）+ HTML 引用 meta（Highwire/Google Scholar）+ 正文抽取（标题/作者/年份/DOI/摘要）。
3. **成功判定**：有效标题（>8 字、无导航关键词、非纯哈希）+ 作者或年份至少其一 + 学术信号（有 DOI / 可信出版商 / arXiv URL）。
4. **富化**：OpenAlex（DOI 或按标题/作者/年份反查）+ Crossref（被引、参考文献、补全元数据）。
5. **入库**：按 canonical key（DOI 优先，否则 URL）去重 upsert；分配 display_index；生成 APA/ACM；写 provenance（session_id、role、时间戳）；同步兼容导出。
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
- 唯一字段：**参考文献格式** `citation_format`（下拉：`apa` / `acm`，默认 `apa`）。
  - 提示："影响引用抽取与综述参考文献章节格式。"
  - 仅在变更（dirty）时启用"保存"，成功提示"个人偏好已保存"。
- 接口：
  - `GET /api/settings/personal/preferences` → `{ citation_format }`
  - `PUT /api/settings/personal/preferences`（body `{ citation_format }`）
- 持久化文件：`/config/personal.preferences.json`；保存后失效本地缓存。

---

## 4. 设置 — 管理员（`/settings/admin/*`）

### 4.1 配置体系与优先级
- **系统设置（管理员）**：凭据 / 实例 / 能力 / Prompts / 存储，落盘 `/config/system.*.json`。
- **个人设置**：引用格式，落盘 `/config/personal.preferences.json`。
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
| `personal.preferences.json` | 个人偏好（引用格式） |
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

---

## 6. 非功能性需求
- **无强制数据库**：参考实现可纯本地文件（JSON/JSONL/Markdown）+ FileLock 运行；可选 Turso 云端 SQLite。
- **并发安全**：所有共享文件写入加锁、原子替换。
- **流式优先**：综述/进度必须真流式（SSE 透传，避免代理缓冲；前端 rAF 批渲染 + 120s 看门狗）。
- **秘钥安全**：API 返回一律掩码，明文只存服务端配置文件 / env。
- **成本可见**：检索/抓取/LLM 均可能产生第三方费用，UI 不隐藏并行度等放大成本的设置。
- **国际化**：界面文案中文为主（可扩展），引用格式支持 APA/ACM 切换。

---

## 7. 复制开发验收清单（节选）
- [ ] 四列布局、响应式宽度、Artifact 开合收窄主区。
- [ ] 会话 CRUD + 置顶 + 本地激活会话恢复。
- [ ] SSE 流式 + 流程卡片（13 种类型）+ 日志行展开 + 检索进度树 + 完成栏 CTA。
- [ ] Composer：多行输入、回车发送、链接上传（首轮禁用）、停止、静默提示、并行度芯片。
- [ ] 意图路由 6 类 + 计划确认门 + 澄清卡。
- [ ] Artifact 四 Tab（大纲/综述/矩阵/文献）+ 综述版本下拉 + 导出。
- [ ] 文献库两栏 + 搜索/筛选/标签 + 卡片徽标 + 详情五 Tab + DOI/标签编辑 + 刷新元数据 + 引用复制（APA/ACM）。
- [ ] 引用抽取流水线（出版商识别、屏蔽源、成功判定、Crossref/OpenAlex 富化、去重 upsert、provenance）。
- [ ] 个人设置（引用格式）+ 管理员五页（概览/凭据/实例/能力/Prompts/存储）+ 掩码 + 测试 + 优先级合并。
- [ ] 统一响应结构、原子写、FileLock、看门狗、掩码安全。

---

*本说明书基于 LitPilot 现有实现编写，目标是行为等价复制。像素值、文案、文件路径为参考实现取值，复制方可在保持交互契约一致的前提下调整。*
