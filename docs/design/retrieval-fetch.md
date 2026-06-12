# 检索与抓取管线设计

`web_search` → 去重合并 → `web_fetch` 的全链路：来源模式、并行策略、统一抓取队列、统计口径。

## 总览

```
[理解 / 子主题拆分]
        ↓
literature_search_plan ──→ 多 pass 检索（按主题或按源）
        ↓
literature_search_merge ──→ 语料去重、junk 过滤
        ↓
relevance_filter（LLM）──→ 剔除低相关命中（`literature_relevance_filter`）
        ↓
FetchCoordinator ──→ 用户 URL 与检索命中共享并行池
        ↓
cite_extract → M1 结构化 → …
```

编排入口：`literature_turn_pipeline.py` · 阶段细节：`literature_phases.py`。

---

## 文献来源模式（`literature_source_mode`）

| 模式 | 有用户 URL | 无用户 URL |
|------|-----------|-----------|
| `merge`（默认） | web_search **不跳过**；抓取队列 **用户链优先** | 仅 web_search |
| `user_only` | **跳过** web_search | 仍 web_search（未强制上传） |

用户 URL 经 Composer「+」或续聊 `intent.new_urls` 注入，归一化后进入 `FetchCoordinator`。

---

## 检索并行策略

### `literature_search_plan` 字段

```json
{
  "queries": ["…"],
  "per_query_max_results": 20,
  "total_passes": 4,
  "search_parallel": 1,
  "topic_parallel": 1,
  "source_parallel": 5,
  "parallel_mode": "by_source" | "by_topic"
}
```

### 按主题并行（`by_topic`）

- 适用：Tavily / native / OpenAlex 等 **单 provider** 多 query
- `topic_parallel = min(search_parallel, total_passes)`
- 各 pass 独立 `stream_search_phase`，事件经 queue **实时** yield

### 按源并行（`by_source`）

- 适用：`search_provider=multi_academic` 且 **≥2 子主题**
- **问题**：多主题 × 5 源同时打同一 API → 429 / 假死
- **模型**：

```
         ┌─ OpenAlex worker ──► 主题1 → 主题2 → …
         ├─ arXiv worker     ──► …
并行 ≤5  ├─ CrossRef worker  ──► …
         ├─ PubMed worker    ──► …
         └─ SS worker        ──► …   （同源任意时刻仅 1 in-flight）
```

- `topic_parallel = 1`，`source_parallel = 5`
- 模块：`source_gate.py`（每源全局 `Lock`）· `iter_multi_pass_by_source_events`（`multi_academic.py`）
- **单主题** multi_academic 仍用原 5 源并行（主题间无冲突）
- **源级重试**：每源最多 `search_retry_count` 次重试（默认 3），间隔 `search_retry_delay_ms`；任意一次返回 hits > 0 即跳出重试；重试在 `source_slot` 锁内执行，保持同源串行语义
- **UI 显示**：同源重试只更新 `source_done` 事件（前端同 label 覆盖），会话框中始终只显示一条记录

### multi_academic 五源

OpenAlex · arXiv · CrossRef · PubMed · Semantic Scholar — 每源独立 worker，SSE：`literature_search_source_start` / `_done`。

---

## FetchCoordinator（统一抓取队列）

**动机（merge 旧瓶颈）**：用户链接等 search 整段结束才 fetch；pipeline 预抓占满 cap，用户链闲置。

### 行为

1. **用户 URL 立即入队** — search 开始时即 `fetch_sources_parallel`（`literature_fetch_user_start`）
2. **检索命中增量入队** — search pass 完成即 `enqueue_search_hits`，与 user fetch **共享** parallel 槽
3. **预算预留** — `upload_reserved = min(len(upload), fetch_cap)`，`search_cap = fetch_cap - upload_reserved`
4. **去重** — canonical URL key；语料已有 + 队列已有跳过（`duplicate_url_skipped`）
5. **优先级** — `parallel_fetch.iter_fetch_sources_parallel(prioritize_upload=True)` 时 upload 源先完成

### 指标（`FetchCoordinatorMetrics`）

| 字段 | 含义 |
|------|------|
| `user_urls_enqueued` | 用户链入队数 |
| `search_hits_enqueued` | 检索命中入队数 |
| `duplicate_url_skipped` | 去重跳过 |
| `user_fetch_done_before_search_end` | 用户链是否在 search 结束前抓完 |

模块：`backend/app/agents/fetch_coordinator.py`。

### 与旧 PipelinedFetchCoordinator 关系

检索阶段 pipeline 预抓已收敛为 **FetchCoordinator 单入口**；`literature_turn_pipeline.run_retrieval_pipeline` 创建 coordinator 并贯穿 search + fetch。

---

## 统计口径（UI 必读）

| 展示 | 正确来源 | 错误做法 |
|------|---------|---------|
| 检索完成 · **纳入 N 篇** | `literature_search_merge.deduped` | 各源 `hits_found` 相加 |
| 主题完成 · **M 篇** | 该 pass 的 `literature_search_pass_done.hits_taken` | 各引擎 `hits_found` 求和 |
| 引擎 · 搜到 X / 取 Y | `literature_search_source_done` 单源字段 | — |

多源检索同一 DOI 会重复计数 raw；**merge 后**才是语料真实篇数。

---

## 流式事件（检索 / 抓取）

| 事件 | 说明 |
|------|------|
| `literature_search_plan` | 计划与 parallel_mode |
| `literature_search_pass_start` | pass 开始 |
| `literature_search_source_start` / `_done` | multi_academic 分源 |
| `literature_search_pass_done` | pass 结束 + 该主题 merge 数 |
| `literature_search_merge` | 全局 merge |
| `literature_fetch_user_start` | 用户 URL 开始抓 |
| `literature_fetch_start` | 单 URL 入队 |
| `literature_progress` | 长阶段 heartbeat（5s） |

前端树构建：`frontend/src/lib/searchProgressTree.ts`。

---

## 能力参数（摘要）

完整硬顶见 [settings-capabilities.md](./settings-capabilities.md)。

| 参数 | 默认 | 说明 |
|------|------|------|
| `search_max_results` | 8 | 合并后命中硬顶 80 |
| `search_parallel` | 1 | 非 multi_academic 时 topic 并行度 |
| `max_fetch_urls` | 5 | 抓取队列硬顶 50 |
| `fetch_parallel` | 3 | 与 coordinator 共享 |
| `fetch_timeout_sec` | 45 | 单 URL |

**四 aspect MOM 推荐**：`search_max_results=40~80`，`max_fetch_urls=15~25`。

---

## 测试锚点

- `test_multi_academic_source_parallel.py` — 同源单 slot
- `test_multi_academic_search.py` — by_source 事件流
- `test_literature_progress.py` — heartbeat
- `test_literature_workflow.py` — 端到端检索 / fetch
