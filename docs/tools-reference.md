# LitPilot 会话可调用工具（Tools）参考

> 面向复制开发团队：列出 LitPilot 在一次文献综述会话中**可被调用的关键工具/能力**（web_search、web_fetch、引用抽取、论文结构化等），给出**调用入口、签名、返回结构、所用后端/外部服务、是否需 Key、缓存与限流**，并在文末给出**可直接交付的文件清单**与随附说明。
>
> 后端为 Python（FastAPI）。工具均为 `async`。配置项经 `app/agents/agent_settings.py` 注入（详见各工具"配置项"）。

---

## 0. 工具总览

| 逻辑工具 | 入口函数（文件） | 作用 | 需 Key |
|----------|------------------|------|--------|
| **web_search** | `web_search_query()` · `tools/web_providers.py` | 学术/网络检索，多后端 | 视后端 |
| **web_fetch** | `web_fetch_url()` / `web_fetch_url_with_meta()` · `tools/web_providers.py` | 抓取 URL/PDF 正文 | 否（jina 可选） |
| **citation_extract** | `extract_and_persist_batch()` · `skills/citation_extractor.py` | 从页面抽取书目并入库（APA） | 否（S2 可选） |
| **paper_attributes** | `extract_attributes_batch()` · `skills/paper_attributes.py` | LLM 结构化论文字段 | 需 LLM |
| **metadata_fetch** | 多个函数 · `tools/metadata_fetch.py` | 取摘要/OA PDF/DOI 元数据 | 否 |
| **pdf_text** | `pdf_bytes_to_text()` · `tools/pdf_text.py` | PDF 字节 → 文本/Markdown | 否 |
| **source_resolve** | `resolve_fetch_url()` 等 · `tools/source_resolve.py` | 落地页 → 直链 PDF | 否（S2 可选） |

学术子检索源（被 `multi_academic` 并行编排，也可独立调用）：**arXiv / Crossref / PubMed(PMC) / Semantic Scholar / OpenAlex**。

---

## 1. web_search（统一检索）

**入口：** `tools/web_providers.py`
```python
async def web_search_query(
    query: str, *,
    provider: str = "native",        # tavily|brave|openalex|native|multi_academic
    api_key: str = "",
    max_results: int = 8,
    search_depth: str = "advanced",  # 仅 tavily：basic|advanced
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict[str, Any]
```
**返回（跨后端归一化）：** `{"results": [{"url","title","snippet", ...}], "answer": ""}`；`multi_academic` 还含 `source_counts`、`per_source`、`raw_found_total`、`hits_taken`。

**后端选择（`normalize_search_provider`，默认 `multi_academic`）：**
| provider | 后端文件 | 需 Key | 说明 |
|----------|----------|--------|------|
| `tavily` | `providers/tavily.py` | Tavily | 通用，支持 search_depth |
| `brave` | `providers/brave.py` | Brave | 用 `site:` 注入域名过滤 |
| `openalex` | `providers/openalex.py` | 无 | 学术索引，倒排摘要重建 |
| `native` | `providers/native_search.py` | 无 | DuckDuckGo HTML 抓取 |
| `multi_academic` | `providers/multi_academic.py` | S2 可选 | arXiv+Crossref+PMC+OpenAlex+S2 并行 |

**multi_academic 额外能力：** `iter_search_events()`（逐源流式事件 `source_start/source_done/complete`）、`iter_multi_pass_by_source_events()`（多主题多 pass、跨 pass 去重源）。

**缓存：** `cached_web_search()`（`tools/cached_tools.py` + `ttl_cache.py`），键 = provider+query+参数。
**过滤：** `tools/search_hits.py`（junk 主机/写作广告/非论文文件过滤、`include_domains` 硬过滤、归一化；含 `ACADEMIC_SEARCH_DOMAINS` 32 域、`DEFAULT_EXCLUDE_DOMAINS` 14 域）。
**配置项：** `get_web_search_provider`、各 provider key、`get_s2_api_key`。

---

## 2. web_fetch（统一抓取）

**入口：** `tools/web_providers.py`
```python
async def web_fetch_url(
    url: str, *,
    provider: str = "native",            # native|jina
    api_key: str | None = None,          # jina key
    timeout: float = 60.0,
    pdf_extract_backend: str | None = None,  # pymupdf4llm|pypdf
    s2_api_key: str | None = None,
) -> str                                 # 纯文本/markdown，≤120,000 字

async def web_fetch_url_with_meta(...) -> dict  # 同上，返回带元数据信封
```
**`_with_meta` 返回：** `{"text","final_url","resolved_pdf_url","is_pdf","provider","pdf_extract_backend","via_jina","metadata_only"}`。

**后端：**
- `native`（`providers/native_fetch.py`）——**5 段流水线**：①API 摘要（OpenAlex/Crossref/PMC/S2）→ ②Unpaywall 解析 OA PDF → ③httpx 直连（PDF/HTML/OJS，手动跟随重定向≤10、magic bytes 判 PDF）→ ④Jina 兜底（反爬）→ ⑤仅元数据（OpenAlex 标题+DOI）。`fetch_bytes()` 返回 `FetchResult`。
- `jina`（`providers/jina.py`）——Jina Reader，`Accept: text/markdown`，arxiv `/abs/`→`/pdf/`。

**依赖：** `metadata_fetch.py`（①②⑤）、`source_resolve.py`（落地页→PDF、S2 记录）、`pdf_text.py`（PDF 抽取）。
**缓存：** `cached_web_fetch()`。
**配置项：** `get_web_fetch_provider`、`get_pdf_extract_backend`、`get_jina_reader_api_key`、`get_s2_api_key`、`get_fetch_parallel`。

---

## 3. 学术子检索源（可独立复用）

统一形态：`async def search(query, *, limit=8, min_year=2019, ...) -> list[dict[str,str]]`，命中归一化为 `{url,title,snippet,source}`（`academic/_hit.py`）。

| 源 | 文件 | 需 Key | 限流/节流 |
|----|------|--------|-----------|
| arXiv | `academic/arxiv.py` | 无 | 1 req/3s（`api_pacing.py`）+ 指数退避×4，按 CS 分类与年份过滤 |
| Crossref | `academic/crossref.py` | 无（礼貌 email） | 无显式节流；仅元数据 |
| PubMed/PMC | `academic/pubmed.py` | 无 | ~3 req/s（`api_pacing.py`）；esearch+esummary 两步 |
| Semantic Scholar | `academic/semantic_scholar.py` | 可选 | 无 key 3.5s/req、有 key 1.1s/req（`ss_rate_limit.py`）；429 退避 |
| OpenAlex | `providers/openalex.py` | 无 | 无 |

**共用件：** `academic/source_gate.py`（每源单并发互斥）、`academic/query_sanitize.py`（剥离中日韩字符，学术 API 对混合查询匹配差）、`api_pacing.py` / `ss_rate_limit.py`（节流与 429 退避，含预算上限 `BackoffBudgetExhausted`）。

---

## 4. citation_extract（引用抽取与入库）

**入口：** `skills/citation_extractor.py`
```python
async def extract_and_persist_batch(
    hits: list[dict[str,str]], *,
    fetch_api_key: str | None = None,
    timeout: float = 60.0,
    max_items: int = 20,
    citation_format: CitationFormat = "apa",   # 本项目固定 APA
    session_id: str = "",
    session_title: str = "",
) -> list[CitationRecord]

async def extract_citation_from_url(url, *, fetch_api_key, title_hint, timeout, s2_api_key) -> CitationRecord
```
**`CitationRecord` 字段：** `title, authors, year, venue, doi, url, abstract, publisher, success, error`。

**流程：** 识别出版商（屏蔽 elsevier/researchgate/google_scholar）→ 出版商 API 元数据（arXiv Atom / S2）→ 抓页取 Highwire `citation_*` meta → 正文兜底（标题/作者/DOI/摘要正则）→ 分层合并（API>HTML meta>正文）→ 成功判定（标题 +（作者或年份）+ 学术信号）→ 去重入库 → 生成 **APA** 引用。批量并行抽取后再并行 OpenAlex/Crossref 富化。
**依赖：** `skills/citation_meta.py`（出版商元数据、Highwire 解析、`merge_metadata_layers`、作者解析）、`web_fetch`（`cached_web_fetch`）、入库层 `library.upsert_citation`（不在本工具单元内）。

---

## 5. paper_attributes（论文结构化，LLM）

**入口：** `skills/paper_attributes.py`
```python
async def extract_attributes_batch(llm, jobs: list[PaperExtractionJob], *, parallel: int = 3) -> list[PaperRecord]
async def extract_paper_attributes(llm, *, title, body, cite) -> dict[str, Any]
```
**抽取字段：** `problem, method, datasets, findings, limitations, keywords`（title+作者+年份+正文≤6000 字 → LLM JSON）。LLM 失败有规则兜底（标题取关键词、摘要作问题陈述）。
**依赖：** LLM 客户端（JSON 模式）、`schemas/paper_record.py`。

---

## 6. 辅助工具单元
- **metadata_fetch.py**：`try_api_abstract_fetch`、`resolve_oa_fetch_urls`(Unpaywall)、`try_metadata_only_fallback`、`try_jina_reader_fetch` + DOI/PMC/SSRN/arXiv 取数与归一化、各类 TTL 缓存。
- **pdf_text.py**：`pdf_bytes_to_text(raw, *, backend="pymupdf4llm", max_chars=120_000)`（pymupdf4llm 优先，pypdf 兜底；校验 `%PDF-`）。注意 pymupdf4llm/PyMuPDF 的 Artifex 商用许可。
- **source_resolve.py**：`resolve_fetch_url`、`resolve_semantic_scholar_fetch_url`、`resolve_landing_page_to_pdf_url`、`resolve_pdf_from_html`（Highwire/pdfjs/OJS）。
- **web_search_domains.py**：`validate_search_domains`（allow 与 block 不可并存）、`filter_hits_by_domains`。
- **cached_tools.py / ttl_cache.py**：检索/抓取 TTL 缓存与键归一化。

---

## 7. 会话中的典型调用链（`agents/literature_phases.py`）
1. 检索：`cached_web_search(query, provider="multi_academic", max_results, include/exclude)` → `apply_literature_hit_filters()`。
2. 抓取：对每条命中 `cached_web_fetch(url, provider="native", timeout, pdf_extract_backend)`，`iter_fetch_sources_parallel()` 并行。
3. 引用：`extract_and_persist_batch(fetch_hits, max_items=20, citation_format="apa")`，逐条发工具事件。
4. 结构化（可选）：`extract_attributes_batch(llm, jobs, parallel=3)`。

---

## 8. 外部依赖与 Key 一览
| 能力 | 必需 Key | 可选 Key | 免费/公开 |
|------|----------|----------|-----------|
| web_search · tavily | Tavily | — | — |
| web_search · brave | Brave | — | — |
| web_search · openalex / native | — | — | ✓ |
| web_search · multi_academic | — | Semantic Scholar | ✓（arXiv/Crossref/PMC/OpenAlex 免费） |
| web_fetch · native | — | Jina、S2 | ✓（Unpaywall/NCBI/OpenAlex 免费） |
| web_fetch · jina | Jina | — | — |
| citation_extract | — | S2 | ✓ |
| paper_attributes | — | — | ✓（需 LLM 客户端） |

---

## 9. 可直接交付给新团队的文件清单

> 这些工具单元**与业务/会话逻辑解耦度高**，可作为参考实现直接交付。建议**只读参考**，不要求二进制兼容。路径相对 `backend/`。

**A. web_search + web_fetch 核心（建议整体交付）**
```
app/agents/tools/web_providers.py          # 统一入口/分发
app/agents/tools/cached_tools.py           # 检索/抓取缓存包装
app/agents/ttl_cache.py                    # TTL 缓存实现
app/agents/tools/search_hits.py            # 命中过滤/归一化 + 默认域名常量
app/agents/tools/web_search_domains.py     # 域名校验/过滤
app/agents/tools/metadata_fetch.py         # 摘要/OA/DOI 元数据
app/agents/tools/source_resolve.py         # 落地页→PDF 解析
app/agents/tools/pdf_text.py               # PDF→文本
app/agents/tools/providers/__init__.py
app/agents/tools/providers/tavily.py
app/agents/tools/providers/brave.py
app/agents/tools/providers/openalex.py
app/agents/tools/providers/native_search.py
app/agents/tools/providers/native_fetch.py
app/agents/tools/providers/jina.py
app/agents/tools/providers/multi_academic.py
app/agents/tools/providers/academic/__init__.py
app/agents/tools/providers/academic/_hit.py
app/agents/tools/providers/academic/arxiv.py
app/agents/tools/providers/academic/crossref.py
app/agents/tools/providers/academic/pubmed.py
app/agents/tools/providers/academic/semantic_scholar.py
app/agents/tools/providers/academic/source_gate.py
app/agents/tools/providers/academic/api_pacing.py
app/agents/tools/providers/academic/ss_rate_limit.py
app/agents/tools/providers/academic/query_sanitize.py
```

**B. 引用抽取技能（依赖 A 的 web_fetch；入库层需自实现）**
```
app/skills/__init__.py
app/skills/citation_extractor.py
app/skills/citation_meta.py
```

**C. 论文结构化技能（需自带 LLM 客户端与 PaperRecord schema）**
```
app/skills/paper_attributes.py
app/schemas/paper_record.py
```

**D. 配套文档（已在本仓库，可一并给）**
```
docs/WebSearchTool/      # web_search 语义说明
docs/WebFetchTool/       # web_fetch 语义说明
docs/literature-workflow.md
docs/tools-reference.md  # 本文件
```

---

## 10. 交付时需随附给新团队的说明

1. **依赖适配**：以上文件 `import` 了少量本项目模块：
   - `app/agents/agent_settings.py`（配置注入：provider 选择、各 Key、pdf backend、并行度）——交付时请一并给该文件，或让对方用自己的配置层实现同名 getter（见 §0/§1/§2 列出的 `get_*`）。
   - `citation_extractor.py` 依赖 `library.upsert_citation`（入库持久化）——**入库层不在工具单元内，需对方自实现**（接口：接收 `CitationRecord` 去重写入）。
   - `paper_attributes.py` 依赖一个 **LLM 客户端**（JSON 模式 `chat/completions`）与 `schemas/paper_record.py`。
2. **Python 依赖**：`httpx`、`pymupdf` + `pymupdf4llm`（或 `pypdf` 兜底）、`filelock`（缓存/入库用到时）。pymupdf4llm 基于 PyMuPDF（Artifex），**商用需许可**，可改用 `pypdf`。
3. **API Key 与免 Key 路线**：默认 `multi_academic`(搜索)+`native`(抓取) **全程免 Key**（arXiv/Crossref/PMC/OpenAlex/Unpaywall/DDG）。需要更高质量/配额时再配 Tavily/Brave/Jina/Semantic Scholar。
4. **限流契约（务必照搬）**：arXiv 1 req/3s、PMC ~3 req/s、S2 3.5s(无 key)/1.1s(有 key)、每学术源单并发；429 指数退避带预算上限。不遵守会被封禁。
5. **检索查询规范**：学术 API 用英文查询（`query_sanitize` 会剥离中日韩字符）。
6. **缓存语义**：检索/抓取均有 TTL 缓存，键含 provider+参数；复现要保持同键同结果。
7. **本项目约定**：引用格式固定 **APA**（`citation_format="apa"`）；抓取正文上限 120k 字；fetch 默认 5 段兜底，单 URL 失败回退检索 snippet，不阻断整轮。
8. **法律/合规**：尊重各数据源（Crossref/OpenAlex/Unpaywall/arXiv/PMC/S2/Tavily/Brave/Jina）服务条款与配额；DDG HTML 抓取属灰区，生产建议改用正式检索 API。

---

*本文件基于 `backend/app/agents/tools/` 与 `backend/app/skills/` 现有实现整理，签名以代码为准。*
