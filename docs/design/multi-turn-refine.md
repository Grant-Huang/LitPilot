# 多轮精化设计

## 三层迭代

| 层 | 用户动作 | intent | 精化对象 |
|----|----------|--------|----------|
| 证据 | 补充检索、上传 URL | `expand_search` / `supplement` | corpus |
| 结构 | 多 aspect brief、改章节 | 首轮 / outline | outline.json |
| 表达 | 改写法、只改某章 | `refine_gen` / `regen_only` | 正文 + gen_constraints |

**原则**：一轮只做一类事。

## 意图路由（续聊）

| intent | 行为 |
|--------|------|
| `new_topic` | 完整管线 |
| `supplement` | 增量 fetch |
| `expand_search` | 增量 web_search |
| `refine_gen` | 复用语料，累积约束，可章节级 refine |
| `regen_only` | 重写，不追加约束 |
| `query_corpus` | 短答，不重写综述 |
| `defer_generate` | 只更新语料 |

`gen_constraints` 持久化于 `sessions/{id}/meta.json`。

## 章节级 refine（P0）

触发：`refine_gen`/`regen_only` + `outline.json` + `review-latest.md`

解析示例：

- 「只重写第二章，改为表格」
- 「重写其二，其余保留」

未指定章节 → 全章重跑（分节流式）。

## 推荐剧本（四 aspect MOM）

1. 首轮：完整 brief → 分主题检索 → 分章初稿  
2. 「第二章 trust 文献偏少，expand_search…」  
3. 「只重写其二，表格对比…，其余保留」  
4. `query_corpus` 核实事实  
5. 「只修订第四节…」

## SSE 反馈

- `literature_clarification` — 首轮歧义 / 检索零命中 / 大纲确认暂停（`kind`: `first_turn` | `search_zero` | `outline_confirm`）
- `literature_section_refine` — partial / full  
- `literature_refine_report` — 缺节、待核实  
- 聊天 toast — 子主题数、大纲章节数、澄清提示

续聊回合经 **后台 Task** 推送 SSE；离开 `/chat` 后返回需全量重放，见 [task-streaming.md](./task-streaming.md)。
