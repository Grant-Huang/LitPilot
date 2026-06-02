# LitPilot 架构

## 分层

- **@meso.ai/ui**（npm：`@meso.ai/ui` / `@meso.ai/types`）：三栏布局、SSE 流式消息、Artifact、WorkflowTimeline
- **LitPilot 前端**：会话、文献库、设置页
- **LitPilot 后端**：`literature_workflow` DAG、文件存储、无 SQL

## 数据目录（`data/`）

| 路径 | 用途 |
|------|------|
| `config/agent.json` | 非敏感 Agent 设置 |
| `sessions/` | 会话索引 + 每会话 `meta.json` / `messages.jsonl` |
| `refs/ref-list.txt` | APA 引用追加列表 |
| `refs/index.json` | 文献库结构化索引 |
| `artifacts/{session_id}/` | 生成的综述 Markdown |
| `pdfs/` | 可选 PDF 缓存 |

敏感 Key 优先来自 `.env`。

## 工作流

见 [literature-workflow.md](./literature-workflow.md)。

## 设计文档

见 [design/README.md](./design/README.md)（M1–M3、能力参数、多轮精化）。
