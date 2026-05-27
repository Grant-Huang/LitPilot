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

## 上下文分栏

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

## Planner 设置（`data/config/agent.json`）

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `use_llm_planner` | `true` | 是否用 LLM 做理解与过程解说 |
| `think_mode` | `lite` | `off` / `lite`（A+C+E）/ `full`（A–G，D 每 5 篇或 8s） |
| `think_use_reasoning` | `false` | MiniMax 国内版：原生推理流进思考区 |
| `think_model` | 空 | 留空=与主 LLM 相同 |
| `think_max_tokens_per_phase` | `280` | 单检查点解说 token 上限 |

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
