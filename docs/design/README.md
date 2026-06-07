# LitPilot 设计文档

面向开发者与高级用户的系统设计说明。日常使用请参阅应用内 **帮助中心**（侧栏用户菜单 → 帮助中心）。

| 文档 | 说明 |
|------|------|
| [overview.md](./overview.md) | 架构分层、数据目录、Meso SSE |
| [**literature-pipeline-v2.md**](./literature-pipeline-v2.md) | **文献管线 v2（减法版，目标架构）** |
| [literature-pipeline.md](./literature-pipeline.md) | ~~M1–M3~~ v1 文献管线（待 v2 落地后 deprecated） |
| [retrieval-fetch.md](./retrieval-fetch.md) | ~~检索并行~~ v1 检索抓取（待 deprecated） |
| [task-streaming.md](./task-streaming.md) | 后台任务、SSE 持久化、/chat 重连与 rehydration |
| [chat-experience.md](./chat-experience.md) | 主会话 P0–P4：宽度、流式反馈、Workflow UI |
| [sprint-3-checklist.md](./sprint-3-checklist.md) | Sprint 3 PR 拆分与验收（P1） |
| [settings-capabilities.md](./settings-capabilities.md) | web_search / web_fetch / Prompts 能力与硬顶 |
| [web-providers.md](./web-providers.md) | Tavily / native / multi_academic 等提供方映射 |
| [multi-turn-refine.md](./multi-turn-refine.md) | ~~多轮精化~~ v1 意图路由（见 v2 文档） |
| [turso-migration.md](./turso-migration.md) | 任务与会话存储迁 Turso |

产品工作流细节见 [../literature-workflow.md](../literature-workflow.md)。

## 阅读顺序（新同学）

1. [overview.md](./overview.md) — 全局
2. [literature-pipeline-v2.md](./literature-pipeline-v2.md) — 单轮与多轮怎么跑（目标）
3. [task-streaming.md](./task-streaming.md) + [chat-experience.md](./chat-experience.md) — 前端怎么接
4. v1 参考：[literature-pipeline.md](./literature-pipeline.md) + [multi-turn-refine.md](./multi-turn-refine.md)（迁移期）
