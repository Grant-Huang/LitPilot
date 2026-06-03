# UI 路由

| 路径 | 说明 |
|------|------|
| `/` | → `/chat` |
| `/chat` | 主会话 + 右侧 Artifact |
| `/library` | 文献库（ref-list + PDF） |
| `/settings` | → `/settings/personal` |
| `/settings/personal` | 个人偏好（引用格式、计划确认） |
| `/settings/admin` | 管理员配置（凭据 / 实例 / 能力 / Prompts） |

帮助中心为侧栏弹窗（非独立路由），内容见 `frontend/src/content/help/`。

Artifact 展开状态保存在 `localStorage`：`litpilot:artifact-visible`。
