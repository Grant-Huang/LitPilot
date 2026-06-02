# 文献管线设计（M1–M3 + P0）

## 混合编排模型

- **骨架固定**：fetch → cite → attributes → outline → 章节×N → refine → deliver
- **章节动态**：按大纲 `sections` 展开 workflow 节点
- **`outline_mode=off`**：回退 4 节点 legacy + 一次性生成

## M1 · 文献结构化（AttributeTree lite）

- 时机：cite 之后、写作之前（`enable_paper_attributes`，默认开）
- 输出：`corpus.json` → `paper_index`（problem / method / findings / keywords…）
- 用途：大纲挂载、分章写作材料

## M2 · 大纲驱动分章

### decompose

规则解析「其一…其二…」→ `ResearchSubTopic` 列表。

### 分主题检索

≥2 子主题时：**每子主题一轮 Tavily**，URL 去重合并（优先于 query expansion）。

### mount

关键词打分将 `paper_index` 挂到 `OutlineSection.mounted_paper_ids`。

### 分节写作

`stream_section_generate` 按章流式输出 → `stitch_review_sections` 拼接。

持久化：`sessions/{id}/outline.json`  
Artifact：`literature-outline+json`

## M3 · 后处理

`post_refine_mode=lite`：去套话、缺节检测、「待核实」统计 → `literature_refine_report`

## P0 · 章节级 refine

`refine_gen` / `regen_only` + 已有大纲 + `review-latest.md`：

1. `parse_refine_target_section_ids` — 「只重写第二章 / 其二」
2. 未命中章节从上一版切分复用（workflow 节点 `skipped`）
3. 命中章节注入【上一版本章稿】+【修订要求】

Monolithic 路径：整篇 revise 注入上一版 excerpt（6000 字）。

## 关键模块

| 模块 | 路径 |
|------|------|
| 编排入口 | `app/agents/literature_turn.py` |
| 子主题拆分 | `app/agents/research_decompose.py` |
| 大纲 | `app/agents/literature_outline.py` |
| 分章写作 | `app/agents/literature_section_writer.py` |
| 章节 refine | `app/agents/section_refine.py` |
| 后处理 | `app/agents/literature_post_refine.py` |
