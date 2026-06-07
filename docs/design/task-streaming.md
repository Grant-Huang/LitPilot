# 后台任务与 SSE 流设计

文献回合从「浏览器直连 SSE」演进为 **持久化后台任务**：多 worker 安全、离开 `/chat` 可继续、回来可重建 UI。

## 模型

```
POST /api/tasks  →  create TaskRecord (pending)
        ↓
LiteratureTaskRegistry.create_and_start
        ↓
stream_literature_turn → 事件 append 到 task event log
        ↓
GET /api/tasks/{id}/stream?since=N  →  SSE 重放 + 订阅新事件
```

| 状态 | 含义 |
|------|------|
| `pending` | 已创建，待 worker 领取 |
| `running` | 执行中 |
| `completed` / `failed` / `cancelled` | 终态 |

存储：`TaskStore`（文件 `backend/data/tasks/` 或 Turso，见 [turso-migration.md](./turso-migration.md)）。

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks` | 创建任务；可带 `session_id`、`fetch_urls`、`literature_source_mode` |
| GET | `/api/tasks/active` | 当前用户活跃任务列表 |
| GET | `/api/tasks/{id}/status` | 状态快照 |
| GET | `/api/tasks/{id}/stream?since=` | SSE；`since` 为已消费 event 序号 |
| DELETE | `/api/tasks/{id}` | 取消（`cancel_requested`） |

模块：`backend/app/api/tasks.py` · `backend/app/tasks/literature_tasks.py` · `backend/app/tasks/task_store.py`。

---

## 事件持久化

- 每个 SSE 事件写入 task event log，单调递增序号
- `since=0`：从头重放（用于 UI 重建）
- `since=N`：仅推送序号 > N 的事件（断线续传）
- 标准 Meso 事件 + LitPilot extension（`literature_*`）均持久化

进度映射：`STAGE_PROGRESS` / `LIT_PROGRESS_STAGE` 将 stage 名映射为 `progress` 百分比与 `stage` 枚举（understanding / searching / …）。

---

## 前端架构

```
LiteratureTaskContext     — activeTask、eventSeq、refreshFromServer
LiteratureStreamContext   — SSE 连接、liveMessages、send/stop
ChatSessionContext        — sessions、messages.jsonl
```

发送：`tasksApi.create` → `connectTaskStream` → `useBatchedSSEStream`。

---

## 重连与 Rehydration

### 离开 `/chat`

- `LiteratureStreamProvider` 在 `!isChat` 时 **abort** 流（任务仍在后端运行）
- 侧栏 / 导航可显示 pending 指示（`LitPilotAppShell`）

### 回到 `/chat`

1. Mount effect：`refreshFromServer()` + `reloadSessionMessages(activeSessionId)`
2. 若 `activeTask` 为 running 且 session 匹配：
   - **`connectTaskStream(taskId, 0, preserveState=false)`** — 全量重放
   - 原因：Provider remount 后 `streamState` 为空；`since=lastSeq + preserveState=true` 无法重建 Workflow / trace

### 切换会话

- 切换 `activeSessionId` 时 abort + reset 本地流状态
- **不**用其他 session 的 activeTask 拉回当前 session（`activeTask.sessionId === activeSessionId` 门禁）

### 任务完成

- 终态后 `loadSessions` + `handleSelectSession`，从 `messages.jsonl` 物化 assistant 消息（含 `executionTrace`）
- `ASSISTANT_RELOAD_ATTEMPTS` 轮询直到持久化消息就绪

### 用户消息展示

- 历史气泡始终渲染 user `content`（`chatMessageMap.ts`）
- 流式结束前 pending user 文本保留在 `liveMessages`

---

## 运维

| 环境变量 | 默认 | 说明 |
|---------|------|------|
| `LITPILOT_TASK_SWEEP_ENABLED` | 1 | 陈旧任务清扫 |
| `LITPILOT_TASK_SWEEP_SEC` | 30 | 清扫间隔 |
| `LITPILOT_TASK_STALE_SEC` | 600 | running 超时 **requeue 为 pending** 并重跑（user 消息在 create 时写入一次，重跑幂等） |

---

## 与直连 SSE 的差异

| 项 | 旧模式 | 任务模式 |
|----|--------|---------|
| 连接 | 单次 HTTP SSE | 可断开重连 |
| 跨页 | 丢失 | 后端继续 + 重放恢复 |
| 取消 | abort fetch | DELETE task |
| 多 worker | 单进程 | TaskStore 锁 + worker_id |

---

## 相关文档

- 会话体验（宽度、静默）：[chat-experience.md](./chat-experience.md)
- 检索事件 schema：[retrieval-fetch.md](./retrieval-fetch.md)
- 文献管线 M1–M3：[literature-pipeline.md](./literature-pipeline.md)
