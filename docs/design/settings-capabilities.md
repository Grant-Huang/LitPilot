# 设置与能力设计

配置入口：**管理员配置** → 能力卡片；综述 Prompt / 大纲 / 后处理在 **Prompts** 页。

## web_search（Tavily）

| 参数 | 默认 | 硬顶 | 说明 |
|------|------|------|------|
| `tavily_max_results` | 8 | **80** | 多轮检索合并后的命中上限 |
| `tavily_retry_count` | 0 | 3 | API 异常重试 |
| `include_domains` | 学术域名列表 | — | 白名单；可关 `enforce_domain_filter` |
| `exclude_domains` | 垃圾域 | — | |
| `search_depth` | advanced | basic/advanced | |
| `enable_junk_filter` | true | — | 标题/摘要噪声过滤 |
| `enable_query_expansion` | false | — | LLM 扩展多 query（与分主题检索二选一优先） |
| `expansion_count` | 3 | 4 | 扩展条数 |

### 多 aspect brief 的检索算术

4 个子主题、`tavily_max_results=80` 时：

- 每轮 `per_query = max(2, 80 // 4) = 20`
- 合并去重后 ≤ **80** 条（实测常有重叠，例如 ~70）

### 与抓取的关系

检索命中 ≠ 全文材料。`max_fetch_urls`（默认 5，硬顶 **50**）决定 Jina 抓取队列长度。

**典型 MOM 四 aspect 推荐**：`tavily_max_results=40~80`，`max_fetch_urls=15~25`。

## web_fetch（Jina）

| 参数 | 默认 | 硬顶 |
|------|------|------|
| `max_fetch_urls` | 5 | 50 |
| `fetch_parallel` | 3 | 8 |
| `fetch_timeout_sec` | 45 | 120 |
| `max_source_chars` | 14000 | 50000 |

## literature_source

| 模式 | 行为 |
|------|------|
| `merge` | Tavily + 用户 URL 合并 |
| `user_only` | 有上传 URL 时跳过 Tavily |

## prompts

| 参数 | 默认 | 说明 |
|------|------|------|
| `enable_paper_attributes` | true | M1 结构化 |
| `outline_mode` | lite | off / lite / full |
| `post_refine_mode` | lite | off / lite |
| `review_system_prompt_template` | 空=内置 | `{fmt_label}` 占位符 |

## 个人设置

- `citation_format`：apa / acm
- `plan_confirm`：开启后在大纲生成完毕时暂停，用户确认后再进入撰写（`resume_mode=generate_only`）；首轮歧义 / 检索零命中也会触发澄清（见工作流文档）

## runtime 桥接

`app/storage/runtime_settings.py` 将 v2 capabilities + personal 合并为 flat dict，供 `agent_settings.py` 读取。
