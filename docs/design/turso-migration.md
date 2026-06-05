# LitPilot → Turso 持久化升级路径

## 目标

- **开发/测试（Vercel Hobby）**：会话、消息、配置、文献库元数据跨 Lambda 一致，消除 404。
- **商业化**：在同一套表结构上扩展多租户、计费、审计，避免二次迁移。

## 架构原则

1. **单一入口**：业务代码继续 `get_store()` / `LibraryStore()`，不扩散存储判断。
2. **分阶段切换**：`LITPILOT_STORAGE_BACKEND=file|turso|hybrid`，默认 `file` 保证现有测试不变。
3. **JSON 列过渡**：library item、session meta 初期用 `*_json` 存完整对象，减少首版改造面；稳定后再规范化列。
4. **大文件后置**：PDF / `sources/*.md` 阶段 3 仍走本地或 `/tmp`；元数据进 Turso。

```
┌─────────────┐     get_store()      ┌──────────────────┐
│  API / Agent│ ───────────────────► │ StorageFactory   │
└─────────────┘                      └────────┬─────────┘
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                   FileStore            TursoStore           HybridStore
                   (本地/dev)          (Vercel 生产)        (Turso + 本地 blobs)
```

## 你需要做的事（一次性）

### 1. 注册 Turso 并创建数据库

```bash
# macOS
brew install tursodatabase/tap/turso
turso auth login
# 查看可用区域（可选，带延迟）
turso db locations
turso db locations --show-latencies

# 创建库（--location 不是 --region；省略则自动选最近区域）
turso db create litpilot-dev --location nrt   # 东京；国内也可试 sin（新加坡）
# 若已有多个 group，需指定：turso db create litpilot-dev --group <group-name>

turso db show litpilot-dev --url
turso db tokens create litpilot-dev
```

记下：

- `TURSO_DATABASE_URL`（形如 `libsql://litpilot-dev-xxx.turso.io`）
- `TURSO_AUTH_TOKEN`

### 2. 环境变量策略（Vercel + 本地 `.env`）

| 环境 | 配置位置 | 说明 |
|------|----------|------|
| **Vercel 开发/生产** | 后端项目 Dashboard → Environment Variables | 冷启动锚点；Serverless 实例重启后必须能连 Turso |
| **本地开发** | 项目根 `.env`（**已 gitignore**，勿提交） | 与 Vercel 使用相同键名；`python-dotenv` 启动时自动加载 |

```bash
# 复制 .env.example → .env，填入真实值（仅本机）
LITPILOT_STORAGE_BACKEND=turso
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
LITPILOT_DATA_DIR=./data
```

管理员 **概览 · 存储** 可保存 URL/Token 覆盖项（运行期生效并写入 Turso），**不能替代** Vercel env 完成冷启动。

本地未启用 Turso 时可省略上述三项，默认 `file` 模式写入 `backend/data/`。

### 3. 初始化 Schema（自动化）

```bash
cd backend
uv sync
python3 scripts/turso_setup.py   # 使用 httpx 走 Turso HTTP API，无需 libsql/cmake
```

### 4. （可选）导入本地 `data/` 历史

```bash
python scripts/migrate_files_to_turso.py --data-dir ./data
```

### 5. Vercel 后端环境变量（必填，与本地 `.env` 键名一致）

| 变量 | 值 |
|------|-----|
| `LITPILOT_STORAGE_BACKEND` | `turso` |
| `TURSO_DATABASE_URL` | Turso 控制台 URL |
| `TURSO_AUTH_TOKEN` | Token（**仅后端**，勿放前端） |
| `LITPILOT_DATA_DIR` | 可保留 `/tmp/litpilot-data`（hybrid 阶段 PDF 缓存） |

本地 `.env` 保留相同 Turso 配置便于联调；**不要**把含 Token 的 `.env` 提交到 Git（已在 `.gitignore`）。

前端 **无需** Turso 变量；仍只需 `BACKEND_URL`。

### 6. 验证

```bash
pytest tests/test_turso_storage.py -v
# 手动：创建会话 → 刷新 → 拉 messages 不 404
```

---

## 分阶段实施（开发顺序）

| 阶段 | 范围 | 用户可见效果 | 预估 |
|------|------|--------------|------|
| **P0** ✅ | Schema + HTTP 连接 + 脚本 + 工厂 | 基础设施 | **已完成** |
| **P1** ✅ | sessions / messages / artifacts / corpus / outline | 聊天 404 消失 | **已完成** |
| **P2** ✅ | config v2（credentials / instances / capabilities / preferences） | 设置页跨请求稳定 | **已完成** |
| **P3** ✅ | library 元数据 + tags | 文献库列表稳定 | **已完成** |
| **P4** ✅ | sources/PDF → `blob_files` + 本地缓存 hybrid | 全文/PDF 跨 Lambda | **已完成** |
| **P5** ✅ | `tenant_id` 列 + `LITPILOT_TENANT_ID` 过滤 | 多租户脚手架 | **已完成** |

每阶段合并条件：

- 对应 pytest 通过
- `LITPILOT_STORAGE_BACKEND=turso` 下手动冒烟
- Vercel 部署分支更新 env

---

## 表结构（P0–P3）

见 `backend/app/storage/schema/001_core.sql`。

| 表 | 对应原 FileStore |
|----|------------------|
| `sessions` | `sessions/{id}/meta.json` + index |
| `session_messages` | `messages.jsonl` |
| `session_documents` | `corpus.json`, `outline.json` |
| `session_artifacts` | `artifacts/{id}/review-latest.md` 等 |
| `config_documents` | `config/system.*.json`, `personal.preferences.json` |
| `library_meta` + `library_items` | `refs/library.json` |

---

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `LITPILOT_STORAGE_BACKEND` | `file` | `file` / `turso` / `hybrid` |
| `TURSO_DATABASE_URL` | — | Turso libsql URL |
| `TURSO_AUTH_TOKEN` | — | 访问令牌 |
| `LITPILOT_DATA_DIR` | `./data` | file/hybrid 本地根目录 |

---

## 商业化移植成本（选 Turso 后）

| 能力 | 做法 |
|------|------|
| 扩容 | Turso Developer $4.99/月起，或迁 Postgres（SQL 相近） |
| 多租户 | `sessions.tenant_id`、`library_items.tenant_id` 列 + RLS 或应用层过滤 |
| 大文件 | 元数据 Turso + R2/S3 指针（`blob_files.storage`） |
| Vercel | Hobby 可继续；高流量再 Pro |

**无需**为持久化单独升 Vercel Pro。

---

## 回滚

1. Vercel 将 `LITPILOT_STORAGE_BACKEND` 改回 `file`（仅适合本地；Vercel 上仍会丢数据）。
2. Turso 数据保留，可随时再切 `turso`。

---

## 相关文件

- `backend/app/storage/schema/001_core.sql` — DDL
- `backend/app/storage/turso_db.py` — 连接与迁移执行
- `backend/app/storage/backend.py` — 工厂
- `backend/scripts/turso_setup.py` — 建表
- `backend/scripts/migrate_files_to_turso.py` — 本地 data 导入
