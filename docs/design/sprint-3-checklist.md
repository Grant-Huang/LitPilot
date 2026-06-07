# Sprint 3 · P1 PR Checklist

目标：**Inline Narrative** + **折叠扁平化** + 检索树收尾。不含 P2（Artifact CTA / 回到底部 FAB）。

设计依据：[chat-experience.md](./chat-experience.md) P1 节。

---

## 基线（开 PR 前）

- [ ] `./scripts/test-gates.sh` 全绿
- [ ] 本地跑一轮四 aspect MOM brief，截图留作 **before**（1920 / 1440 各一张）
- [x] 确认 Sprint 1–2 已合：`literature_progress`、宽度 68%、`SearchProgressView` 骨架

## 已实现（本 Sprint 只做收尾，勿重复造轮子）

| 项 | 现状 |
|----|------|
| 工具 log 行 | `formatToolLogLine` + `LitPilotToolStep`（`→ outcome`、原始响应折叠） |
| Turn 级总折叠 | `TurnWorkflowBlock` 已去掉外层 `<details>` |
| 阶段卡片 | `WorkflowCardView`：running 自动展开、done 默认折叠 + `__inline-summary` |
| 前缀槽位 | `litpilot-wf-card__marker`（✓ / ▸ / ▾ / spinner） |
| 检索树 | `searchProgressTree.ts` + `SearchProgressView` |
| 步 dedup | `workflowStepFilter.ts` |
| 统计口径 | `deduped` / `hits_taken`；aggregate 展示 merge 纳入篇数 |
| 遗留 UI | `LitPilotProcessTrace.tsx` 已删除；orphan `.litpilot-process*` CSS 已清理 |
| Extension → UI | `deriveLiveFieldsFromStream` + `buildTurnWorkflowFromStream` 单一路径 |
| 流状态机 | `literatureStreamPhase.ts`（idle / pending / streaming / settling / done / error） |
| Task 幂等 | user 消息在 `create_and_start` 写入一次；`persist_user_message=False` 重跑 |

---

## PR-1 · 工具结果 Inline Narrative 收尾（P1-A）

**范围**：统一所有工具展示路径；主界面零 JSON；原始响应仅二级入口。

### 改动

- [ ] **`toolLabels.ts`**
  - [x] `web_search` / `web_fetch`：专用分支已实现
  - [ ] 其它 tool（`extract_attributes`、`cite` 等）：补 `formatToolLogLine` 分支或强化通用 fallback
- [x] **`LitPilotProcessTrace.tsx`** — 已删除（无引用）
- [x] **`LitPilotAssistantTurn.tsx`** — 已去掉无效 `defaultCollapsed`
- [ ] **`workflowStepFilter.formatInlineLogLine`**：extension 步 title 与 tool 步语义对齐（避免「检索中…」与 tool 行双行重复）

### 测试

- [ ] 扩展 `turnCompletion.test.ts` / 新建 `toolLabels.test.ts`：`web_search` / `web_fetch` / error / pending 快照
- [ ] 断言：`rawDetail` 仅在 JSON 无法解析或 error 时出现

### 验收

- [ ] 展开「文献检索 / 抓取网页」卡片：**无**居中 card、**无** `<pre>` 默认可见
- [ ] 每行形态：`主文案 → outcome`（Claude Code log 风）
- [ ] 「原始响应」点击后才出现 `<pre>`

### 预估

~1 PR，**300–500 行**（含删 ProcessTrace + 测试）

---

## PR-2 · 折叠扁平化（P1-B）

**范围**：流式仅 running 展开；历史 turn 全阶段单行摘要；去掉第三层无意义折叠。

### 改动

- [x] **`WorkflowCardView.tsx`**
  - [x] running 自动展开；done 默认折叠（`manualOpen` 可点开）
  - [x] 折叠态 head **不显示** `进行中` pill（仅 `open && running`）
- [ ] **`summarizeWorkflowCard`（`turnCompletion.ts`）**
  - [x] `search`：优先 merge `deduped`
  - [ ] `fetch` / `understand` / `brief` / `generate`：补全单行摘要规则
- [ ] **`TurnWorkflowBlock.tsx`**
  - [ ] 历史 turn：`TurnCompletionBar` 与卡片摘要去重（产品决策待定）
- [x] **`LitPilotThinkFold`**：非 running 时默认折叠（`collapsed={!(streaming && isRunning)}`）

### 测试

- [ ] `turnCompletion.test.ts`：`summarizeWorkflowCard` 各 type + merge extension
- [ ] 可选：`WorkflowCardView` 轻量 render test（running 展开 / done 折叠）

### 验收

- [x] **Live turn**：仅 1 张 `running` 卡片展开，已完成阶段一行摘要
- [ ] **历史 turn**：进入会话默认全折叠，可点开单卡
- [x] 折叠 / 展开：前缀槽 1.25rem 固定宽（P1-C 回归）

### 预估

~1 PR，**250–400 行**

---

## PR-3 · 检索层级树与统计口径（P1-D 收尾）

**范围**：多主题 + multi_academic 树正确；禁止 raw 加总；与 tool 步不重复。

### 改动

- [x] **`searchProgressTree.ts`** — merge `deduped`、pass_done 不用源加总
- [x] **`SearchProgressView.tsx`** — aggregate 展示「纳入 N 篇」
- [x] **`turnWorkflow.ts`** — merge 事件写入 search 卡 `summary`
- [ ] 主题行展示 pass 级 `hits_found`（根聚合已用 `mergedDeduped`）

### 测试

- [ ] 扩展 `searchProgressTree.test.ts`：4 主题、多源 hit 故意不等 → 主题行 **≠** raw 加总
- [ ] fixture 含 `literature_search_merge.deduped: 47`

### 验收

- [x] 四 aspect brief：**不会出现**「检索完成 · 80 篇」类 raw 加总（除非 merge 真实为 80）
- [x] 树形缩进清晰；展开主题不影响阶段标题列对齐

### 预估

~1 PR，**200–350 行**

---

## PR-4 · 样式收敛 + 门禁（横切）

**范围**：删冗余 CSS；统一 log /token；文档与门禁。

### 改动

- [x] **`meso-platform.css`** — 删除 `.litpilot-process*`、`.litpilot-composer__urls` orphan 规则
- [ ] 合并 `litpilot-tool-step__*` 与 `litpilot-log-line__*` 重复规则
- [ ] `litpilot-wf-card__inline-summary`：与 title 同一 baseline，muted 色，不换行截断
- [x] **`chat-experience.md`** / **`literature-workflow.md`** / **`overview.md`**：Artifact 仅输出物、Task SSE 已更新
- [ ] 可选 Storybook / 截图：`docs/design/sprint-3/` 放 after 截图

### 测试

- [ ] `./scripts/test-gates.sh`
- [ ] 手动：1280 / 1440 / 1920；Artifact 开/关；live + 历史各 1 turn

### 验收

- [x] 无视觉回归：前缀槽 1.25rem 固定宽（与 P1-C 一致）
- [x] 前端 bundle：删除 ProcessTrace 后无 dead import

### 预估

~1 PR，**150–250 行**（可与 PR-1 合并若改动面小）

---

## 建议合并顺序

```text
PR-1（工具 log） → PR-3（检索树/统计） → PR-2（折叠） → PR-4（CSS + 文档）
```

PR-3 在 PR-2 前：先保证 `summarizeWorkflowCard` / 树统计数据源一致，再调折叠摘要文案。

---

## 明确不在 Sprint 3（已实现或进 Sprint 4）

- [x] `TurnCompletionBar` 行动条 → 打开 Artifact（P2-A，已实现）
- [x] 回到底部 FAB（已实现 `LitPilotScrollToBottom`）
- [x] Composer 来源 chip（merge / user_only，已实现）
- [ ] 轮次结束 Brief 摘要 bubble（P4）

---

## Definition of Done（Sprint 3 整体）

- [ ] 4 个 PR 合并后 `main` 上 `./scripts/test-gates.sh` 绿
- [ ] [chat-experience.md](./chat-experience.md) P1 核心项 ✅（工具 log / 折叠 / 检索树）
- [ ] 产品 sign-off：1920 截图 live + 历史 turn 各 1 张
- [ ] 无 open issue：JSON 主展示、80 篇误统计、Turn 三层折叠

---

## 风险与依赖

| 风险 | 缓解 |
|------|------|
| 历史消息无 `extensionLog`，树为空 | 历史 turn 仅 tool 行 + summary，acceptable |
| 去掉 ProcessTrace 影响未知引用 | `rg LitPilotProcessTrace` 全仓为 0 再删 |
| 折叠后信息过少 | `TurnCompletionBar` + inline summary 双保险 |
| merge 事件晚于 search 卡折叠 | `turnWorkflow` 流式更新 `card.summary` on extension |
