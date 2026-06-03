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
理解+意图 → 检索(Tavily) → 抓取(Jina) → 引用抽取 → [结构化] → [大纲] → [分章写作] → [后处理] → 交付
```

- **理解 / 检索**：左侧思考区 + stage 时间线
- **抓取之后**：右侧 Artifact「流程」步骤列表
- **多 aspect brief**：额外展示「大纲」Tab

## SSE 事件（Meso v1.0）

标准：`stage`、`think`、`text`、`artifact`、`tool_call`、`workflow_node`  
扩展：`literature_intent`、`literature_clarification`、`literature_subtopic_plan`、`literature_outline`、`literature_section_refine` 等

## 前端 Artifact 侧栏

| Tab | 内容 |
|-----|------|
| 流程 | 执行步骤与状态（非 SVG DAG） |
| 大纲 | 章节与子主题（outline 路径） |
| 综述 | Markdown 流式正文 |
| 文献 | 本回合收录，可跳转引用 |
