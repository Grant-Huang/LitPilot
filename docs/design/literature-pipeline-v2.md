# Literature Pipeline v2 — 精简设计文档

> 审计日期：2026-06-07  
> 基于现有实现做减法，而非重写。取代旧版 literature-pipeline.md、retrieval-fetch.md、multi-turn-refine.md 中的编排语义。

---

## 一、三大子流程总览

```
用户消息
   │
   ▼
Intent Router (规则 + LLM fallback)
   │
   ├─ new_topic / subtopic_change
   │     │
   │     ▼
   │   [ web_search ]  per-subtopic 串行推进
   │     A: 子主题规划 + 关键词 (LLM, Checkpoint A)
   │     B: 并行多源搜索（multi_academic / brave / tavily）
   │     C: per-subtopic LLM 二次过滤 → narrate C
   │     │ ↓ 每个子主题完成搜索+过滤后立即启动 fetch
   │     ▼
   │   [ web_fetch ]   并行线程 per-subtopic
   │     D: 并行 HTTP fetch / PDF 提取（五阶段管线）
   │     E: metadata enrich → narrate E
   │     F: 失败条目 → 保留元数据，不进综述
   │     ▼
   │   [ generation ]
   │     G: 逐章生成综述（section-by-section）
   │     H: 矩阵生成（按需，query_corpus 触发）
   │
   ├─ review_refine
   │     └─ 只走 generation（部分章节 or 全量），不重走 search/fetch
   │
   ├─ append_urls
   │     └─ 只走 fetch → enrich → LLM 打子主题标签
   │        不自动重生成综述，短答提示用户
   │
   ├─ query_corpus
   │     └─ LLM 直接回答，不走 search/fetch/generate
   │
   └─ short_answer   ← 非明确意图
              告知用户如需增减子主题请明确说明
```

---

## 二、Intent 表

| Intent | 触发条件 | search | fetch | generate | 备注 |
|--------|---------|:------:|:-----:|:--------:|------|
| `new_topic` | 第一轮，或明确换题 | ✅ | ✅ | ✅ 全量 | Composer `+` 禁用 |
| `subtopic_change` | 显式"加/改子主题" | ✅ 仅变更子主题 | ✅ 仅变更子主题 | ✅ 对应章节 | 需 diff，见§三 |
| `review_refine` | 明确修改/重写综述 | ❌ | ❌ | ✅ 部分 or 全量 | 版本号规则见§六 |
| `append_urls` | 多轮中上传 URL | ❌ | ✅ | ❌ | 打标签 → 短答提示 |
| `query_corpus` | 问文献库内容 | ❌ | ❌ | ❌ | 轻量 LLM 回答 |
| `short_answer` | 其他意图模糊 | ❌ | ❌ | ❌ | 引导说"加/改子主题" |

**Intent 检测规则（规则优先，LLM fallback）：**
- 第一轮 → `new_topic`
- 消息含 URL → `append_urls`（已去重）
- 中文"加/增加/新增子主题 XXX"、"修改子主题 N 为 XXX" → `subtopic_change`
- 中文"修改/优化/重写第 N 章" → `review_refine`
- 有语料 + 明确疑问句 → `query_corpus`
- **其余 → `short_answer`**（当前默认为 query_corpus，**需修改**）

---

## 三、Subtopic Diff（subtopic_change）

### 判定"变化"原则
**只响应用户显式说明的操作**：
- "增加一个子主题：XXX" → 新子主题，执行完整 search→fetch
- "修改子主题 N 为 XXX" → 替换子主题，执行完整 search→fetch
- 其他措辞 → `short_answer`，回复：
  > "如需增加或修改子主题，请明确说明，例如：'增加一个子主题：大语言模型的安全对齐'"

### Diff 逻辑
```
新子主题列表 vs 旧子主题列表
  ├─ 新增 → search + fetch + 写对应新章节
  ├─ 内容变更 → search + fetch + 重写对应章节
  └─ 未变化 → 语料复用，不重搜
```

**当前状态**：`subtopic_change` intent 已存在，但重搜**全部**子主题 → **待改为 diff 后选择性重搜**

---

## 四、Per-Subtopic 状态机

```
PENDING
  │ 规划完成
  ▼
SEARCH_RUNNING
  │ raw_count ≥ 1 → FILTER_RUNNING
  │ raw_count = 0 → SKIPPED（直接跳过，不报错）
  ▼
FILTER_RUNNING  ← LLM 二次过滤
  ▼
FETCH_RUNNING   ← 并行线程（此时其他子主题可并行推进搜索）
  │ 全部成功/部分成功 → DONE
  │ 全部失败 → FETCH_FAILED（保留元数据，标 cite_in_review=False）
  ▼
DONE
```

---

## 五、SSE 事件清单（精简后）

### 保留事件

```
subtopic_plan          子主题规划完成 {count, subtopics[]}

per-subtopic:
  search_done          {subtopic_id, title, raw_count, duration_ms}
  filter_done          {subtopic_id, kept_count}
  fetch_done           {subtopic_id, ok, failed, skipped}

stage                  阶段状态 {name, state: active|done}
text                   旁白/解说 {delta, delivery: chat|process}
artifact               综述/矩阵 delta 流 {id, lang, delta, done, version_id}
session_title          会话标题更新
literature_intent      意图声明 {intent, ...flags}
turn_start / turn_end  轮次边界
tool_call / tool_result 工具调用（调试，UI 可折叠）
```

### 删除 / 合并

| 事件 | 处置 |
|------|------|
| `literature_search_pass_start/done/hits` | 合并进 `search_done` |
| `literature_search_source_start/done` | 删除（per-source 进度 UI 不需要） |
| `literature_progress`（旧 ticks） | 删除，`stage` 替代 |
| 所有 `LEGACY_EXTENSIONS` 中的旧事件 | 清理 call site |

**当前状态**：`LEGACY_EXTENSIONS` 过滤器已过滤旧事件 ✅；call site 仍有冗余调用待清理。

---

## 六、版本策略

| 操作 | 版本规则 | 示例 |
|------|---------|------|
| `new_topic` | v(n+1) | v1 |
| `subtopic_change`（有新章节） | v(n+1) | v1 → v2 |
| `review_refine` 部分章节 | 旧版号 + 累加字母 | v2 → v2a → v2b |
| `review_refine` 全量重写 | v(n+1) | v2 → v3 |

**当前实现**：`review_version.py` ✅

---

## 七、用户上传 URL

### 第一轮（new_topic）
- Composer `+` 按钮禁用（`uploadDisabled=true`）
- **当前实现**：✅

### 多轮（append_urls）
```
检测 URL
  → 并行 fetch（优先用户上传）
  → metadata enrich
  → LLM 打子主题标签（tag_items_to_subtopics）
  → 文献入库（cite_in_review=False，不自动进综述）
  → 短答：
    "已获取 N 篇文献，归属子主题 [A, B]。
     建议可根据新文献更新第 2、3 章。"
```

**当前实现**：✅（subtopic_pipeline.py append_urls 分支）

---

## 八、文献库数据结构

```
CorpusPaperRecord
  ├─ url / doi / arxiv_id          # 标识符
  ├─ title / authors / year
  ├─ abstract
  ├─ subtopic_tags: List[str]       # 多标签，支持跨子主题
  ├─ fetch_ok: bool
  ├─ cite_in_review: bool           # fetch 失败 → False
  ├─ pdf_available: bool            # 是否有源文件（UI 图标用）
  └─ structured:                    # 可选，见§十
       problem / method / findings
```

### 跨子主题去重
- Canonical URL 规范化（scheme/domain/path）
- 同一 URL 多子主题 → 合并 `subtopic_tags`
- **当前实现**：✅

---

## 九、PDF 下载策略

**触发条件**（有 DOI / arXiv ID / OA URL）：
1. OpenAlex / CrossRef / Semantic Scholar 返回 OA PDF URL → 直接下载
2. Unpaywall 返回 OA URL → 下载
3. arXiv ID 存在 → 尝试 `arxiv.org/pdf/{id}`
4. 直接 HTTP → Jina Reader fallback

**失败处理**：
- 静默失败（不在会话中报错）
- `pdf_available=false`，文献库 UI 图标显示
- 用户可在文献库补充后手动触发

**当前实现**：native_fetch 五阶段管线 ✅；文献库图标待实现

---

## 十、结构化字段（problem / method / findings）

**建议：保留，降级为可选**

- 矩阵生成（synthesis matrix）依赖这三个字段
- fetch 成功但结构化提取失败 → fallback：`abstract[:500]` 填充 `findings`，其余留空
- 矩阵生成时字段缺失 → 用「—」占位
- 不阻断综述生成

---

## 十一、配置项收敛

### UI 显示（用户可调）

| 配置项 | 默认值 | 范围 |
|--------|--------|------|
| LLM provider / model / api_key | — | — |
| `search_max_results` | 20 | 1–80 |
| `max_fetch_urls` | 5 | 1–50 |
| `fetch_parallel` | 3 | 1–8 |
| `fetch_timeout_sec` | 45 | 10–120 |
| `search_retry_count` | 3 | 0–3 |
| `citation_format` | apa | apa/acm |
| `search_include/exclude_domains` | — | — |
| planner/router/review/pipeline LLM 独立配置 | — | — |

### 内部参数（不在 UI 显示）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `search_depth` | advanced | |
| `search_enforce_domain_filter` | true | |
| `search_enable_junk_filter` | true | |
| `max_source_chars` | 14000 | |
| `fetch_retry_count` | 0 | |
| `fetch_retry_delay_ms` | 500 | |

### 删除

| 配置项 | 理由 |
|--------|------|
| `orchestrator_use_reasoning` | 硬编码 False |
| `orchestrator_mode` | v2 不用 orchestrator 模式 |
| `orchestrator_max_tokens_per_phase` | 同上 |
| `literature_source_mode` | 已删除 ✅ |

---

## 十二、模块映射与删除清单

### 核心模块（保留）

| 模块 | 路径 | 作用 |
|------|------|------|
| `literature_turn.py` | agents/ | 入口，意图分发 |
| `literature_intent.py` | agents/ | Intent 检测 |
| `literature_subtopic_pipeline.py` | agents/ | Per-subtopic 状态机 |
| `literature_phases.py` | agents/ | search/fetch/cite 执行 |
| `literature_turn_generate.py` | agents/ | 综述生成入口 |
| `literature_section_writer.py` | agents/ | 逐章写作 |
| `section_refine.py` | agents/ | 部分章节重写 |
| `review_version.py` | agents/ | 版本号管理 |
| `parallel_fetch.py` | agents/ | 并行 fetch 线程池 |
| `native_fetch.py` | agents/tools/ | 五阶段 fetch 管线 |
| `prompt_registry.py` | agents/ | 提示词模板 |
| `session_corpus.py` | agents/ | 语料数据结构 |
| `subtopic_tagging.py` | agents/ | append_urls 打标签 |
| `task_store.py` | tasks/ | 后台任务持久化 |

### 清理清单（死代码）

| 符号 / 模块 | 处置 | 状态 |
|------------|------|------|
| `get_orchestrator_use_reasoning()` | 删除 | ❌ 待做 |
| `get_orchestrator_mode()` | 删除 | ❌ 待做 |
| `get_orchestrator_max_tokens()` | 删除 | ❌ 待做 |
| 重复 `get_review_llm_config()` | 删除重复定义 | ❌ 待做 |
| `FetchNarrationThrottle` | 删除（从未实例化） | ❌ 待做 |
| `LEGACY_EXTENSIONS` filter + call sites | 清理 | ❌ 待做 |
| legacy intent mapping (supplement/refine_gen) | 删除 | ❌ 待做 |
| 废弃 narrate checkpoints B/D/F/F2/G | 已从 PROMPT_SPECS 删除 | ✅ 已做 |
| `literature_source_mode` 全链路 | 已删除 | ✅ 已做 |
| `SidebarTaskBadge` | 已删除 | ✅ 已做 |
| Composer 模式选项卡 | 已删除 | ✅ 已做 |
| Composer hint 文字 | 已删除 | ✅ 已做 |

---

## 十三、已实现 vs 待实现汇总

| 需求 | 状态 | 优先级 |
|------|------|--------|
| 三子流程 search→fetch→generate | ✅ | — |
| 子主题规划 + 关键词（LLM） | ✅ | — |
| 并行多源搜索 | ✅ | — |
| per-subtopic LLM 二次过滤 | ✅ | — |
| Fetch 顺序执行（不与 search 并行） | ✅ | — |
| Fetch 并行线程 | ✅ | — |
| PDF 下载（OA/arXiv/DOI） | ✅ | — |
| 文献元数据库 | ✅ | — |
| 版本化综述（v1/v1a/v1b） | ✅ | — |
| 综述矩阵 artifact | ✅ | — |
| review_refine 部分章节重写 | ✅ | — |
| 多标签（一文多子主题） | ✅ | — |
| append_urls 多轮上传 | ✅ | — |
| 第一轮禁用 URL 上传 | ✅ | — |
| Fetch 失败保留元数据 | ✅（待确认入库） | 中 |
| Search 零命中直接跳过 | ✅ | — |
| query_corpus 轻量意图 | ✅ | — |
| 后台 Task + 断线重放 | ✅ | — |
| **short_answer intent（非明确意图）** | ❌ | **高** |
| **Subtopic diff（只改变更的子主题）** | ❌ | **高** |
| 结构化字段 fallback（abstract 降级） | ❌ | 中 |
| PDF 图标 UI 显示 | ❌ | 低 |
| 单篇手动重新 fetch | ❌ | 低 |
| 删除死代码（orchestrator_* 等） | ❌ | 中 |
| SSE call site 清理 | ❌ | 低 |
