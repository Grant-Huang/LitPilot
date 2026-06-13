# LitPilot 全量 Live E2E 测试报告

生成时间：2026-06-13
测试分支：`main`（`a7c4840`）
测试方式：真实 LLM（DeepSeek）+ 真实学术搜索（arXiv/S2/OpenAlex/CrossRef）+ 真实网页抓取

---

## 一、测试矩阵与结果总览

共 11 个 live 测试，分 3 个文件运行。结果汇总：

| # | 测试 | 文件 | 结果 | 原因分类 |
|---|------|------|------|---------|
| 1 | `test_new_topic_full_pipeline` | e2e | PASS | — |
| 2 | `test_subtopic_change_incremental` | e2e | FAIL | 网络：LLM 路由降级 short_answer |
| 3 | `test_append_urls_bypass_search` | e2e | FAIL | 网络：抓取阶段 Connection error |
| 4 | `test_review_refine_partial_regenerate` | e2e | FAIL | 网络：LLM 路由降级 short_answer |
| 5 | `test_query_corpus_qa` | e2e | PASS | — |
| 6 | `test_short_answer_no_pipeline` | e2e | PASS | — |
| 7 | `test_clarify_natural_trigger` | clarify | PASS | 未触发澄清（软警告） |
| 8 | `test_clarify_forced_trigger` | clarify | PASS | 成功触发 clarification |
| 9 | `test_mom_new_topic` | mom | FAIL | 网络：搜索 0 命中 |
| 10 | `test_mom_followup_query` | mom | FAIL | 网络：第2轮路由 new_topic |
| 11 | `test_append_ref_list_urls` | mom | FAIL | 网络：抓取 Connection error |

**通过率：4/11（36%）**。全部 7 个失败均由同一根因导致：HTTP 代理在测试期间返回 `403 Forbidden`（`httpcore.ProxyError`），使 LLM 调用与学术搜索全部失败。

---

## 二、Bug 定位与修复

### Bug #1（已修复）：`KeyError: 'url'` — append_urls 抓取阶段崩溃

**根因**：`literature_phases.py` 的抓取事件循环中，进度心跳（`tick`）阶段会 yield 一个空 hit 字典 `{}`，但消费端在阶段判断之前就执行了 `url = hit["url"]`，导致 `KeyError: 'url'`。

**触发条件**：当并行抓取无任务完成时，`iter_fetch_sources_parallel` yield `("tick", {}, "", None)`（见 `parallel_fetch.py:112`），消费端立刻崩溃。

**修复**（`backend/app/agents/literature_phases.py:736`）：将 tick 阶段的 `continue` 提前到 `url` 提取之前，并对 url 改用 `.get()`：

```python
        ):
            if phase == "tick":
                yield (
                    "literature_progress",
                    {...},
                )
                continue
            url = str(hit.get("url") or "")
            if phase == "start":
```

**验证**：修复后重跑 `test_append_ref_list_urls`，KeyError 计数从 1 降为 **0**（事件数从 57 增至 148，证明进度心跳不再崩溃）。

### Bug #2（环境问题，非代码）：HTTP 代理 `403 Forbidden`

**现象**：所有依赖 LLM/搜索的测试出现 `httpcore.ProxyError: 403 Forbidden` → `openai.APIConnectionError: Connection error`。

**诊断**：
- 直接 `curl https://api.deepseek.com` 返回 HTTP 401（网络通）
- 直接 `httpx` 调用返回 HTTP 401（网络通）
- 但 pytest 进程内 OpenAI SDK 调用间歇性收到代理 403

**结论**：本机网络环境存在不稳定代理/限速，非代码缺陷。`conftest.py` 的 `inject_seeded_store` 测试因 LLM 路由失败而降级为 `short_answer`，属预期降级行为。

### Bug #3（预存在，非本次引入）：`test_prompt_registry` 单元测试失败

`test_understanding_default_is_domain_agnostic` 断言 prompt 含「过程解说员」，但拉取的提交 `cb0dc1c`（提示词优化）已移除该词。此为上游遗留，与本次改动无关。

---

## 三、各轮测试详情（提示词 + 输出摘要）

### 批次 1：`test_literature_e2e.py`（首轮改用 MOM 提示词）

#### #1 test_new_topic_full_pipeline — PASS

**提示词**：
> 我要写一个与AI原生MOM（制造运营管理）有关的文献综述，包括4个方面：其一，AI原生MOM系统性的定义框架与参考模型。其二，异构机器间信任建立的工程方案与制造知识图谱。其三，多智能体协作、动态知识推理与可组合微服务架构三条研究线索，及其统一的工程整合框架。其四，从传统单体MOM向AI原生MOM的渐进式迁移的工程框架。

**输出摘要**：
- 意图：`new_topic`（正确）
- 子主题拆分：**4 个**，与提示词 4 个方面精确对应
  - thread1: AI原生MOM系统性的定义框架与参考模型
  - thread2: 异构机器间信任建立的工程方案与制造知识图谱
  - thread3: 多智能体协作、动态知识推理与可组合微服务架构
  - thread4: 从传统单体MOM向AI原生MOM的渐进式迁移
- 检索：passes=0, hits_found=0（搜索 API 全部 403）
- 抓取：ok=0, failed=0
- 综述产物：2451 字（LLM 在无检索结果时仍生成框架性综述）
- turn_end：`检索 4 轮 · 纳入 0 篇`

#### #2 test_subtopic_change_incremental — FAIL（网络）

**提示词**：「增加一个关于多模态幻觉的章节」
**输出**：意图被降级为 `short_answer`（LLM 路由因代理 403 失败，回退规则）。事件 8 个，无搜索/抓取。

#### #3 test_append_urls_bypass_search — FAIL（网络）

**提示词**：「补充这篇论文」+ URL `https://arxiv.org/abs/2401.00001`
**输出**：意图 `append_urls`（正确），进入抓取+引用抽取阶段，但 `APIConnectionError: Connection error`。

#### #4 test_review_refine_partial_regenerate — FAIL（网络）

**提示词**：「请把综述中关于检测方法的部分写得更详细一些」
**输出**：意图被降级为 `short_answer`（LLM 路由失败）。

#### #5 test_query_corpus_qa — PASS

**提示词**：「已有文献中关于检测方法主要有哪些？」
**输出**：意图 `query_corpus`（正确，规则引擎匹配），基于 seeded corpus 回答，产物 1131 字。

#### #6 test_short_answer_no_pipeline — PASS

**提示词**：「你好」
**输出**：意图 `new_topic`（首轮规则路由），子主题=`你好`，产物 1755 字。

---

### 批次 2：`test_literature_e2e_clarify.py`

#### #7 test_clarify_natural_trigger — PASS（软警告）

**提示词**：「帮我研究下MOM，越快越好，随便找点相关的就行」
**输出**：
- 意图：`new_topic`
- **未触发 clarification**（LLM 对该模糊输入仍给出 ≥0.7 置信度）
- 子主题：1 个（`帮我研究下MOM...`），raw=0
- 综述产物：1776 字
- 测试通过（设计为软警告：若未触发则记录，不失败）

**说明**：自然触发依赖真实 LLM 给出低置信度，不稳定。forced-trigger 测试提供可靠回归保护。

#### #8 test_clarify_forced_trigger — PASS

**提示词**：MOM 完整提示词 + `LITPILOT_UNDERSTANDING_CONFIDENCE_THRESHOLD=0.95`
**输出**：
- 意图：`new_topic`（正确）
- **成功触发 `clarification` 事件**（选项数：1）
- clarification prompt：`请重新描述您的研究意图：`
- 检索 4 轮，纳入 0 篇（搜索 API 403）
- 综述产物：2451 字

**说明**：阈值强制提升到 0.95 后，任何置信度都无法直接通过，clarification 子循环被可靠触发。事件结构与 explore 阶段分析一致。

---

### 批次 3：`test_literature_e2e_mom.py`

#### #9 test_mom_new_topic — FAIL（网络）

**提示词**：MOM 完整提示词
**输出**：
- 意图：`new_topic`（正确）
- 子主题拆分 2 个（LLM 规划因代理失败降级）
- 搜索：hits_found=0（全部 403）
- 断言失败：`hits_found >= 1`（真实 API 应有命中，但代理 403 导致 0 命中）

#### #10 test_mom_followup_query — FAIL（网络）

**第1轮提示词**：MOM 完整提示词
**第2轮提示词**：「已有文献里多智能体协作的主流框架有哪些？请基于已有文献回答。」
**输出**：第2轮意图被降级为 `new_topic`（应为 `query_corpus`），因第1轮 LLM 失败导致 corpus 未建立，规则引擎判定为首轮。

#### #11 test_append_ref_list_urls — FAIL（网络，KeyError 已修复）

**提示词**：「补充这些参考文献」+ ref-list.txt 前 15 个 URL
**输出**：
- 意图：`append_urls`（正确）
- 抓取阶段：**148 个事件**（修复前 57 个即崩溃）
- `APIConnectionError: Connection error`（抓取真实 URL 时代理 403）
- **KeyError: 'url' 已消除**（修复验证通过）

---

## 四、检索量与来源汇总

> 注：本次运行期间搜索 API 全部被代理 403 拦截，故所有 `hits_found=0`。下表反映的是「网络正常时应能采集」的字段，而非本次实际数值。

| 指标 | 数据来源事件 | 本次实际值 |
|------|-------------|-----------|
| 子主题数 | `literature_subtopic_plan.count` | MOM首轮：4 |
| 每源命中数 | `literature_search_source_done.hits` | 全部 0（403） |
| 聚合命中数 | `literature_search_pass_done.hits_found` | 全部 0（403） |
| 源分布 | `literature_search_pass_done.source_counts` | `{}`（403） |
| 子主题原始命中 | `literature_subtopic_search_done.raw_count` | 全部 0（403） |
| 过滤保留/拒绝 | `literature_subtopic_filter_done.kept_count`/`rejected` | 0/0 |
| 抓取成功/失败 | `literature_subtopic_fetch_done.ok`/`failed` | 0/0 |
| 综述字数 | `artifact` delta 累计 | MOM首轮：2451 |

**信息来源**（搜索 providers）：
- arXiv（`http://export.arxiv.org/api/query`）→ 本次 403
- Semantic Scholar（`api.semanticscholar.org`）→ 本次 403
- OpenAlex（`api.openalex.org`）→ 本次 403
- CrossRef（`api.crossref.org`）→ 本次 403
- PubMed（仅生物医学向）→ 本次未触发

---

## 五、LLM 调用统计

由 `LLMTraceCollector` 采集。本次因代理 403，多数测试 LLM 调用失败，有效调用统计有限：

| 测试 | LLM 调用数 | 总耗时 | 说明 |
|------|-----------|--------|------|
| clarify_natural_trigger | 3 | 4.0s | flash 模型，含 Connection error |
| clarify_forced_trigger | 0（缓存的 clarify 路径） | — | clarification 后走 option[0] |
| new_topic_full_pipeline | — | — | 规划降级，综述生成 |

> 正常网络下，MOM 首轮完整 pipeline 约 15-25 次 LLM 调用（路由×1 + 理解×4 + 搜索精炼×4 + 引用抽取×N + 综述生成×4），预计总耗时 30-90s。

---

## 六、clarify 流程验证结论

1. **触发机制确认**：`clarification` 是 Understand 阶段的置信度门控子循环，不是独立意图。当 `router_result.confidence < LITPILOT_UNDERSTANDING_CONFIDENCE_THRESHOLD`（默认 0.7）时触发。
2. **forced-trigger 可靠复现**：阈值提升到 0.95 后，`clarification` 事件稳定触发，携带 1 个选项（`narration` + `search_aspects`），prompt 为「请重新描述您的研究意图：」。
3. **当前行为**：触发后自动选 option[0] 并 break（不等待前端用户选择），与源码 TODO 一致。
4. **自然触发不稳定**：模糊提示词不一定触发（取决于真实 LLM 置信度），建议以 forced-trigger 作为回归测试。

---

## 七、待办与建议

| 项 | 状态 | 说明 |
|----|------|------|
| `KeyError: 'url'` 抓取崩溃 | **已修复** | `literature_phases.py:736`，tick 阶段提前 continue |
| 代理 403 网络问题 | 环境 | 需在稳定网络/无代理环境重跑以获取真实检索量 |
| `test_prompt_registry` 失败 | 预存在 | 上游 `cb0dc1c` 改 prompt 未同步测试，建议单独修 |
| clarify 自动选 option[0] | 待产品决策 | 当前不等待用户选择，真实前端需改 loop 逻辑 |
| 完整检索量报告 | 待网络恢复 | 网络正常后重跑批次 3 可产出真实 source_counts |

---

## 八、复现命令

```bash
# 全量 live 测试（需网络）
cd backend && .venv/bin/python -m pytest tests/test_literature_e2e.py tests/test_literature_e2e_clarify.py tests/test_literature_e2e_mom.py -m live -v -s

# 单个 clarify 强制触发测试
cd backend && .venv/bin/python -m pytest "tests/test_literature_e2e_clarify.py::test_clarify_forced_trigger" -m live -v -s

# 单元测试门禁（不含 live）
cd backend && .venv/bin/python -m pytest tests/ -q
```
