# 系统概览

## 分层

| 层 | 职责 |
|----|------|
| **@meso.ai/ui** | 三栏布局、SSE 流式、Artifact 面板 |
| **LitPilot 前端** | 会话、文献库、设置、帮助中心 |
| **LitPilot 后端** | `literature_turn` 编排、文件存储、无 SQL |

## 数据目录（`backend/data/`）

| 路径 | 用途 |
|------|------|
| `config/` | v2 凭据、实例、能力、个人偏好 |
| `sessions/{id}/` | `meta.json`、`messages.jsonl`、`corpus.json`、`outline.json` |
| `refs/` | `ref-list.txt`、`library.json` |
| `artifacts/{id}/` | `review-latest.md`、矩阵等 |

敏感 Key 来自凭据配置或 `.env`，不写入 Git。

## 单轮文献管线（概念）

```
理解+意图 → web_search → relevance_filter → web_fetch → 引用抽取 → [结构化] → [大纲] → [分章写作] → [后处理] → 交付
```

- **理解 / 检索**：Workflow 卡片 + think 折叠；长阶段 `literature_progress` heartbeat
- **抓取**：FetchCoordinator 用户链与检索命中共享并行池（见 [retrieval-fetch.md](./retrieval-fetch.md)）
- **执行过程**：主聊天区 Workflow 卡片（`TurnWorkflowBlock`），不在 Artifact 展示
- **Artifact 侧栏**：仅输出物——综述 Markdown、文献矩阵、大纲 JSON、本回合文献列表

## 后台任务

用户发送消息后创建 **TaskRecord**，SSE 经 `GET /api/tasks/{id}/stream` 推送并持久化；离开 `/chat` 任务继续，返回时全量重放重建 UI。详见 [task-streaming.md](./task-streaming.md)。

## SSE 事件（Meso v1.0 + LitPilot 扩展）

**标准**：`stage`、`think`、`text`、`artifact`、`tool_call`、`workflow_node`

**意图 / 结构**：`literature_intent`、`literature_clarification`、`literature_subtopic_plan`、`literature_outline`、`literature_section_refine`、`literature_refine_report`

**检索 / 抓取（流式反馈）**：`literature_search_plan`、`literature_search_pass_start`、`literature_search_source_start` / `_done`、`literature_search_pass_done`、`literature_search_merge`、`literature_fetch_user_start`、`literature_fetch_start`、`literature_progress`

完整 schema 与统计口径见 [retrieval-fetch.md](./retrieval-fetch.md)、主窗展示见 [chat-experience.md](./chat-experience.md)。

## 前端 Artifact 侧栏

| Tab | 内容 |
|-----|------|
| 综述 | Markdown 流式正文（默认） |
| 大纲 | 章节与子主题（outline 路径） |
| 文献 | 本回合收录，可跳转引用 |

不展示 SVG DAG、`workflow-graph` 或执行步骤列表；`workflow-graph` artifact 仅侧栏数据流中剥离，不入主聊天区。
