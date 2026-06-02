# 文献综述工作流

```
router → search (Tavily，可跳过) → fetch (Jina 并行) → cite_extract → generate (LLM) → deliver
```

## 文献来源策略（`literature_source_mode`）

| 模式 | 有用户 URL 列表时 | 无用户 URL 时 |
|------|------------------|---------------|
| `merge`（默认） | Tavily 检索 + **用户链接优先**合并去重后 `web_fetch` | 仅 Tavily |
| `user_only` | **跳过 Tavily**，只抓取用户 URL | 仍执行 Tavily（未强制要求上传） |

用户 URL 通过聊天输入框「+」上传 `.txt` / `.csv` / `.json`，请求体字段 `fetch_urls`。

## 检索与抓取设置

| 配置项 | 作用 |
|--------|------|
| `tavily_max_results` | `web_search` 单次最多返回条数（1–80，默认 8） |
| `max_fetch_urls` | `web_fetch` 队列上限（1–50，默认 5） |
| `fetch_parallel` | Jina 并行并发；**cite 阶段**引用抽取与 Crossref/OpenAlex 元数据补全共用该并发上限 |
| `fetch_timeout_sec` | 单 URL 超时 |
| `tavily_retry_count` | Tavily 请求异常重试 |
| `fetch_retry_count` | 单 URL 抓取异常重试 |
| `fetch_retry_delay_ms` | 重试间隔 |
| `enable_query_expansion` | 是否启用多 query 检索扩展（默认关） |
| `expansion_count` | 扩展检索式数量（1–4，默认 3） |

## 文献结构化（M1 · AttributeTree lite）

cite 之后、generate 之前（`enable_paper_attributes`，默认开）：

1. 对每条成功抓取的 URL 抽取结构化字段：`problem` / `method` / `datasets` / `findings` / `limitations` / `keywords`
2. 写入会话 `corpus.json` 的 `paper_index`（v2）
3. SSE：`stage`「文献结构化」、`tool_call` `extract_attributes`、`literature_paper_index`

多轮续聊时复用语料；仅对 **尚未结构化** 的文献增量抽取，不影响 `refine_gen` / `regen_only` 流式修订。

## 检索扩展（M6）

启用 `enable_query_expansion` 时：

1. 由编排 LLM（或规则回退）生成 2–4 条检索式
2. 分轮 Tavily 检索，按 URL 去重合并，总量不超过 `tavily_max_results`
3. SSE：`literature_search_plan`、`literature_search_merge`

## 大纲驱动分章写作（M2）

`outline_mode`（prompts 能力，默认 `lite`）：

| 值 | 行为 |
|----|------|
| `off` | 固定 4 节点 DAG，一次性 monolithic 生成 |
| `lite` | 检测到「其一…其二…」等多 aspect  brief 时，拆子主题分检、分章写、再拼接 |
| `full` | 始终走大纲 + 分节流式写作（单主题也会拆导言/正文/结论） |

流程（outline 路径）：

```
fetch → cite → attributes → outline → [章节×N 流式] → refine → deliver
```

1. **decompose**：规则解析用户 brief 为 `ResearchSubTopic`（子主题检索式）
2. **分主题检索**：≥2 子主题时各跑一轮 Tavily，URL 去重合并（优先于 query expansion）
3. **mount**：按关键词将 `paper_index` 挂载到各 `OutlineSection`
4. **分节写作**：每章独立 LLM 流式输出，前文摘要衔接
5. SSE：`literature_subtopic_plan`、`literature_outline`（artifact `literature-outline+json`）、按章节 `text` 增量

会话持久化：`sessions/{id}/outline.json`

前端 Artifact 侧栏：

| Tab | 内容 |
|-----|------|
| **流程** | 步骤列表 + 当前进度（替代 SVG DAG；检索/理解在左侧思考区） |
| **大纲** | `literature-outline+json`：子主题、章节、挂载文献数 |
| **综述** | Markdown 正文 |
| **文献** | 本回合收录条目 |

设置页「综述 System Prompt」：`outline_mode`、`post_refine_mode`（带说明 tips）

`refine_gen` / `regen_only` 在有大纲时：

- 解析「只重写第二章 / 其二 / 第 N 章」→ **章节级 refine**（其余章从 `review-latest.md` 复用，graph 节点标记 skipped）
- 注入【上一版本章稿】+【修订要求】到 LLM；无指定章节时仍全章重跑
- SSE：`literature_section_refine`

## 后处理（M3）

`post_refine_mode`（默认 `lite`）在 deliver 前执行规则校验：

- 去除套话结语（「综上所述…」等）
- 检测大纲章节是否在正文中出现
- 统计「待核实」标记

SSE：`literature_refine_report`

---

- `[Tavily]` — 检索摘要
- `[网页材料]` — Jina 正文要点（content_pipeline 压缩）
- `[Citations]` — `ref-list.txt` 中已收录 APA / ACM 条目

## 引用元数据补全（cite_extract）

每条成功抓取的 URL 会：

1. **并行** Jina 抽取 APA/ACM 书目字段（`fetch_parallel` 限流）。
2. **并行** 元数据 enrich：
   - 页面已解析出 DOI → 直接 **Crossref** 补全被引数、他引数、卷期页等；
   - 无 DOI → 用 **标题 + 首作者 + 年份** 调 **OpenAlex** 反查 DOI，再 Crossref enrich。
3. 串行写入文献库（文件锁），并同步 `ref-list` / 导出。

文献库详情页可手工补 DOI；保存时可选 `refresh_crossref` 重新拉 Crossref。无 DOI 时后端 enrich 接口也会尝试 OpenAlex。

## 失败策略

- Tavily 全部失败：终止当轮，提示检查 Key
- 单 URL Jina 失败：跳过，使用 Tavily snippet；`ref-list` 可记 `[FAILED]`
- 引用元数据不足：不写入半条引用，综述中标注「待核实」

## 引用格式

设置页 `citation_format` 支持 `apa`（默认）与 `acm`，影响引用抽取、ref-list 与 LLM 参考文献章节。

## 编排模型设置（`data/config/agent.json`）

编排模型（Orchestrator）负责理解、规划与过程解说；撰写综述用主模型 `llm_model`，两者可分开配置。

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `use_llm_planner` | `true` | 是否用 LLM 做理解与过程解说 |
| `orchestrator_mode` | `lite` | `off` / `lite`（A+C+E）/ `full`（A–G，D 每 5 篇或 8s） |
| `orchestrator_use_reasoning` | `false` | MiniMax 国内版：原生推理流进思考区 |
| `orchestrator_model` | 空 | 编排模型；留空=与主 LLM 相同（建议 MiniMax-M2.7-highspeed） |
| `orchestrator_max_tokens_per_phase` | `280` | 单检查点解说 token 上限 |

检查点 A 与 `route_literature` 合并为 **一次流式 LLM 调用**（叙述 + 末行 JSON）。

| 检查点 | 时机 | lite | full |
|--------|------|------|------|
| A | 理解 + router | ✓ | ✓ |
| B | Tavily 检索前 | | ✓ |
| C | 检索后 | ✓ | ✓ |
| D | 抓取进行中（节流） | | ✓ |
| E | 抓取后 | ✓ | ✓ |
| F | 引用抽取后 | | ✓ |
| G | 综述生成前 | | ✓ |

## Meso SSE

后端 `app/core/streaming.py` 输出 Meso v1.0 envelope；前端 `useSSEStream('/api/chat/literature/execute')`。

执行过程中会推送：
- `stage` — 阶段时间线（理解问题 / 检索 / 抓取 / 引用 / 生成）
- `think` — **Planner 模型流式解说**（默认 lite：理解 / 检索后 / 抓取后）；极短系统注记以 `⟦sys⟧…⟦/sys⟧` 标记并灰色展示
- `tool_call` / `tool_result` — Tavily、引用抽取等
- `workflow_node` — 右侧 DAG 节点状态（配合初始 `workflow-graph` artifact）
- `text` — 综述正文流式增量

右侧 Artifact 在收到 `workflow_node` 后即可展示实时 DAG（`mergeWorkflowRunsIntoGraph`）。

关键事件：`stage`、`tool_call`、`workflow_node`、`artifact`（`workflow-graph` / `markdown`）、`text`、`literature_intent`、`done`。

## 续聊意图（P0–P2）

首轮走完整流程 `new_topic`；后续轮次由 `literature_intent` 路由：

| intent | 说明 | 典型行为 |
|--------|------|----------|
| `new_topic` | 首轮 / 新主题 | 完整 search → fetch → cite → generate |
| `supplement` | 补充 URL / 文件 | 增量 fetch，合并 session corpus |
| `refine_gen` | 调整写作要求 | 复用语料，增强 gen_prompt |
| `regen_only` | 仅重生成 | 同 refine，不追加约束 |
| `expand_search` | 扩展检索 | Tavily 增量 + fetch 新命中 |
| `retry_failed` | 重试失败项 | 仅 fetch 失败 URL |
| `query_corpus` | 文献问答 | 短回答，不生成完整综述 |
| `manage_library` | 库管理 | 删除 / 导出 / 去重 |

SSE 推送 `literature_intent` extension，字段含 `intent`、`defer_generate` 等。

会话 `meta.json` 扩展：`initial_query`、`gen_constraints`、`review_versions`、`last_intent`。
语料快照：`sessions/{id}/corpus.json`。
