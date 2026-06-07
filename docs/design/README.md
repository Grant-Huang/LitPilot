# LitPilot 设计文档

面向开发者与高级用户的系统设计说明。日常使用请参阅应用内 **帮助中心**（侧栏用户菜单 → 帮助中心）。

| 文档 | 说明 |
|------|------|
| [overview.md](./overview.md) | 架构分层、数据目录、Meso SSE |
| [literature-pipeline.md](./literature-pipeline.md) | M1–M3 文献管线、大纲分章、章节 refine |
| [retrieval-fetch.md](./retrieval-fetch.md) | 检索并行（by_source）、FetchCoordinator、统计口径 |
| [task-streaming.md](./task-streaming.md) | 后台任务、SSE 持久化、/chat 重连与 rehydration |
| [chat-experience.md](./chat-experience.md) | 主会话 P0–P4：宽度、流式反馈、Workflow UI |
| [sprint-3-checklist.md](./sprint-3-checklist.md) | Sprint 3 PR 拆分与验收（P1） |
| [settings-capabilities.md](./settings-capabilities.md) | web_search / web_fetch / Prompts 能力与硬顶 |
| [web-providers.md](./web-providers.md) | Tavily / native / multi_academic 等提供方映射 |
| [multi-turn-refine.md](./multi-turn-refine.md) | 多轮会话、意图路由、精化剧本 |
| [turso-migration.md](./turso-migration.md) | 任务与会话存储迁 Turso |

产品工作流细节见 [../literature-workflow.md](../literature-workflow.md)。

## 阅读顺序（新同学）

1. [overview.md](./overview.md) — 全局
2. [literature-pipeline.md](./literature-pipeline.md) + [retrieval-fetch.md](./retrieval-fetch.md) — 单轮怎么跑
3. [task-streaming.md](./task-streaming.md) + [chat-experience.md](./chat-experience.md) — 前端怎么接
4. [multi-turn-refine.md](./multi-turn-refine.md) — 续聊怎么路由
