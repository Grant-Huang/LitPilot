# LitPilot

面向科研人员的**文献综述助手**：基于 [MESO](https://github.com/Grant-Huang/MESO) 三栏交互界面，自动完成学术检索、网页抓取、引用抽取与大模型综述生成。

## 功能概览

| 能力 | 说明 |
|------|------|
| 学术检索 | [Tavily](https://tavily.com/) 搜索，自动增强 arXiv / DBLP 站点偏好 |
| 全文抓取 | [Jina Reader](https://jina.ai/reader/) 并行抓取论文页面正文 |
| 引用抽取 | 从出版商页面提取元数据，写入本地引用库 |
| 综述生成 | 多源材料 + LLM 流式输出结构化综述 |
| 引用格式 | **APA**（默认）与 **ACM**，在设置页切换 |
| 工作流可视化 | 实时 DAG：检索 → 抓取 → 引用 → 生成 → 交付 |
| 会话与文献库 | 无数据库，会话与引用均落盘 `data/` |

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 15、React 19、`@meso.ai/ui`、Ant Design、Tailwind |
| 后端 | FastAPI、httpx、OpenAI 兼容 LLM 客户端 |
| 存储 | 本地文件（JSON / JSONL / Markdown），[filelock](https://pypi.org/project/filelock/) 并发安全 |
| 外部服务 | Tavily、Jina Reader、可选多厂商 LLM |

## 项目结构

```
LitPilot/
├── backend/          # FastAPI 服务
│   ├── app/
│   │   ├── agents/   # 文献综述 DAG、工作流 SSE
│   │   ├── api/      # REST 路由
│   │   ├── skills/   # 引用抽取（APA / ACM）
│   │   └── storage/  # 文件存储
│   └── tests/
├── frontend/         # Next.js 应用（端口 3002）
├── data/             # 运行时数据（gitignore，首次运行自动创建）
│   ├── config/       # agent.json 等配置
│   ├── sessions/     # 会话与消息 JSONL
│   ├── refs/         # ref-list.txt、index.json
│   └── artifacts/    # 生成的综述 Markdown
├── docs/             # 设计说明
└── scripts/          # 开发启动脚本
```

## 环境要求

- **Python** 3.11+（推荐 3.13；仓库内 venv 可能为 3.14）
- **Node.js** 18+ 与 **pnpm**
- **pnpm** 或 **npm**（前端通过 npm 安装 [MESO](https://github.com/Grant-Huang/meso) 的 `@meso.ai/ui` / `@meso.ai/types`）
- API Key：**Tavily**（必填）、**LLM**（必填，Ollama 除外）、**Jina**（可选）

## 快速开始

### 1. 克隆与配置

```bash
cp .env.example .env
# 至少填写：
#   TAVILY_API_KEY=tvly-...
#   OPENAI_API_KEY=sk-...   # 或改用其他 LLM 提供商
```

也可在启动后于 **系统设置** 页保存 Key（写入 `data/config/agent.json`），优先级高于 `.env`。

### 2. 启动（推荐一键脚本）

```bash
chmod +x scripts/start-dev.sh
./scripts/start-dev.sh
```

- 后端默认：`http://127.0.0.1:8001`
- 前端默认：`http://127.0.0.1:3002`

仅启动某一端：

```bash
./scripts/start-dev.sh backend
./scripts/start-dev.sh frontend
```

### 3. 手动启动

**后端**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=$(pwd)
export LITPILOT_DATA_DIR=../data
uvicorn app.main:app --reload --port 8001
```

**前端**

```bash
cd frontend
pnpm install   # 从 npm 安装 @meso.ai/ui、@meso.ai/types
pnpm dev
```

浏览器打开 [http://localhost:3002](http://localhost:3002)，在 **会话** 页描述研究主题并点击「生成综述」。

## MESO 依赖（npm）

前端通过 **npm / pnpm** 安装已发布的 MESO 包（与 [MESO](https://github.com/Grant-Huang/meso) 仓库同源）：

```bash
npm install @meso.ai/ui @meso.ai/types
# 或
pnpm add @meso.ai/ui @meso.ai/types
```

`frontend/package.json` 已声明 `@meso.ai/ui@^2.0.0`、`@meso.ai/types@^1.0.0`；`pnpm-lock.yaml` 锁定具体版本。

若需本地调试 MESO 源码，可临时改为 `file:` 路径，例如：

```json
"@meso.ai/ui": "file:../../projects/meso/packages/meso-ui"
```

LitPilot 侧栏品牌使用 Meso `ThreeColumnLayout` 的 `sidebarLogo` / `sidebarTitle`（白牌 API），其余品牌与业务 UI 均在 LitPilot 内实现。

## 配置说明

### 环境变量（`.env`）

| 变量 | 说明 |
|------|------|
| `TAVILY_API_KEY` | Tavily 检索（必填） |
| `JINA_API_KEY` | Jina Reader（可选，无 Key 仍可用公开 Reader） |
| `LLM_PROVIDER` | `openai` / `zhipu` / `alibaba` / `minimax_intl` / `minimax_cn` / `ollama` |
| `OPENAI_API_KEY` | OpenAI 兼容 API Key |
| `OPENAI_MODEL` | 模型名，默认 `gpt-4o-mini` |
| `OPENAI_BASE_URL` | API 根路径，默认 `https://api.openai.com/v1` |
| `MINIMAX_GROUP_ID` | MiniMax 国内版可选 Group ID |
| `LITPILOT_DATA_DIR` | 数据目录，默认 `./data` |

### 设置页（`data/config/` + 管理员 UI）

- **个人设置**（`/settings/personal`）：引用格式 APA/ACM、`plan_confirm` 计划确认
- **管理员配置**（`/settings/admin`）：凭据、实例、能力、Prompts

旧版 `agent.json` 仍可由 runtime 合并；推荐通过 v2 设置 API 管理。

### 前端代理（`frontend/.env.local`）

```bash
BACKEND_URL=http://127.0.0.1:8001
```

修改后需**重启** `pnpm dev`。

## 文献综述工作流

```
理解问题 → Tavily 检索 → Jina 并行抓取 → 引用抽取 → LLM 综述 → 交付 Artifact
```

- 材料分栏：`[Tavily]` 摘要、`[网页材料]` 正文、`[Citations]` 已收录引用
- 单 URL 抓取失败时回退 Tavily snippet，不阻断整轮
- 引用元数据不足时不写入半条记录，正文中标注「待核实」

详细说明见 [docs/literature-workflow.md](docs/literature-workflow.md)。

### 引用格式示例

**APA**

```
[1] A. Author (2020). Deep Learning. Nature. https://doi.org/10.1038/x
```

**ACM**

```
[1] A. Author. 2020. Deep Learning. Nature. DOI:https://doi.org/10.1038/x
```

## 页面导航

| 路径 | 功能 |
|------|------|
| `/chat` | 文献综述对话与流式输出 |
| `/library` | 引用索引、`ref-list.txt`、PDF 列表 |
| `/settings/personal` | 个人偏好（引用格式、计划确认） |
| `/settings/admin` | 凭据、实例、能力、Prompts |

## API 概览

统一 JSON 响应结构：

```json
{
  "status": "success|error",
  "data": {},
  "message": "optional"
}
```

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/chat/literature/execute` | SSE 文献综述流（Meso v1.0 envelope） |
| `GET` / `POST` | `/api/settings/agent` | 读取 / 保存 Agent 配置 |
| `POST` | `/api/settings/agent/test-tavily` | 测试 Tavily Key |
| `GET` | `/api/sessions` | 会话列表 |
| `POST` | `/api/sessions` | 创建会话 |
| `GET` | `/api/sessions/{id}/messages` | 会话消息 |
| `GET` | `/api/sessions/{id}/review` | 最新综述产物 |
| `GET` | `/api/library/refs` | 引用索引与 ref-list |
| `GET` | `/api/library/pdfs` | PDF 文件列表 |

SSE 请求体示例：

```json
{
  "message": "大语言模型在代码生成中的研究进展",
  "session_id": "可选，省略则自动创建"
}
```

前端通过 `frontend/src/app/api/chat/literature/execute/route.ts` **流式透传** SSE，避免 Next.js `rewrites` 缓冲导致界面长时间无输出。

## 开发与测试

```bash
# 完整门禁（含 Vercel：deploy 种子、后端入口、next build）
./scripts/test-gates.sh

# 仅后端
./backend/scripts/test.sh -q

# 前端类型检查 / Lint
cd frontend
pnpm type-check
pnpm lint
```

## 常见问题

**界面长时间无流式输出**

- 确认使用 Route Handler 透传（`/api/chat/literature/execute`），勿仅用 `next.config` rewrite 代理 SSE。
- 检查 `BACKEND_URL` 与后端端口一致。

**提示未配置 Tavily**

- 在设置页保存 Tavily Key，或在 `.env` 中设置 `TAVILY_API_KEY` 后重启后端。

**端口占用**

- 后端默认 `8001`（`scripts/start-dev.sh` 可通过 `BACKEND_PORT` 覆盖）。
- 前端固定 `3002`。

**API 费用**

- Tavily、Jina、LLM 均可能产生第三方费用，请自行关注各平台用量。

## 许可证

见仓库根目录 LICENSE（如有）。第三方服务使用须遵守各自条款。

## 相关文档

- [文献综述工作流](docs/literature-workflow.md)
- [MESO UI 框架](https://github.com/Grant-Huang/meso)
