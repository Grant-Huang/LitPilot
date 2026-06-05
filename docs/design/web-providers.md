# web_search / web_fetch 提供方设计

## docs 参考实现对照

| docs 目录 | 机制 | LitPilot 能力 | 我们的实现 |
|-----------|------|---------------|------------|
| **`WebSearchTool/`** | Anthropic **`web_search_20250305` 服务端工具**（需 Claude API） | `web_search` | `tavily`（默认）/ `openalex` / **`native`** |
| **`WebFetchTool/`** | 直连 HTTP + HTML→Markdown | `web_fetch` | `jina`（默认）/ **`native`** |

> `docs/ToolSearchTool/` 是 Agent 内「搜 deferred tools」，与文献检索 **无关**。

## WebSearchTool → LitPilot 映射

参考 `WebSearchTool.ts` / `prompt.ts`：

| WebSearchTool | LitPilot |
|---------------|----------|
| `query`（≥2 字符） | 检索 query / `search_query_refiner` 输出 |
| `allowed_domains` | `web_search.params.include_domains` |
| `blocked_domains` | `web_search.params.exclude_domains` |
| 二者不可同时指定 | `web_search_domains.validate_search_domains` |
| `max_uses: 8`（Anthropic 硬编码） | `search_max_results`（1–80，能力页可配） |
| 结果 `{ title, url }[]` | `normalize_search_results` → `{ url, title, snippet }` |

### 为何不能原样移植 WebSearchTool？

WebSearchTool 的 `call()` 是向 **Anthropic Messages API** 挂 `extraToolSchemas: [{ type: 'web_search_20250305', ... }]`，搜索在 **Anthropic 侧**完成。LitPilot 主 LLM 为 OpenAI 兼容 / MiniMax / Ollama，编排层不能假设该 server tool 存在。

因此：

- **默认**：Tavily（等价于「外包索引」）
- **学术**：OpenAlex（免费 DOI/摘要）
- **native**：自研 DuckDuckGo HTML 检索 + 与 WebSearchTool 相同的域名 allow/block 规则（**无需 Key**，反爬与稳定性弱于 Tavily）

## web_fetch（WebFetchTool 参考）

见 `providers/native_fetch.py`：`httpx`、UA、重定向限制、OJS PDF 跟进；正文走 `content_pipeline`。

能力参数 `fetch_provider`：`jina` | `native`。

PDF 正文解析（仅 `native` 直连 PDF 时）：`pdf_extract_backend`

| backend | 依赖 | 说明 |
|---------|------|------|
| `pypdf`（默认） | `pypdf` | MIT，轻量纯文本 |
| `pymupdf4llm` | `pip install -r requirements-optional.txt` | Markdown/表格/版面更佳；**PyMuPDF 在商业/闭源场景需 Artifex 商业许可证** |

未安装 `pymupdf4llm` 时自动回退 `pypdf`。

## web_search 能力参数

```json
"search_provider": "tavily" | "openalex" | "native"
```

| provider | Key | 适用 |
|----------|-----|------|
| `tavily` | Tavily API Key | 通用综述、中文、多域 |
| `openalex` | 无 | 英文学术论文 |
| `native` | 无 | 无 Tavily 时的兜底；域名过滤与 WebSearchTool 一致 |

## 代码入口

- `web_providers.web_search_query` / `web_fetch_url`
- `providers/tavily.py` · `providers/brave.py` · `providers/openalex.py` · `providers/native_search.py`
- `providers/jina.py` · `providers/native_fetch.py`
- `search_hits.py`：检索结果归一化与文献向过滤（各 provider 共用）
- `cached_tools.cached_web_search` / `cached_web_fetch`
- `runtime_settings`: `search_provider`, `fetch_provider`
