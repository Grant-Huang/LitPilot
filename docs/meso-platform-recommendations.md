# LitPilot 致 Meso 团队的平台改进建议

> 来源：LitPilot 在 2025 Q2–Q3 多轮路由健壮性整改 + 流式会话 UI 重设计后，沉淀的可平台化改动建议。
> 受众：Meso 平台 / `@meso.ai/ui` / `@meso.ai/types` 维护团队。
> 目的：降低后续接入 meso 的研究类应用的"重复造轮子"成本，把已经在 LitPilot 验证过的模式回灌到平台。

---

## 0. 一句话总结

LitPilot 接入 meso 后，**业务 UI（process trace / workflow / search progress）整套自建**——`@meso.ai/ui` 只覆盖了 `ChatBubble` / `ThreeColumnLayout` / `ArtifactPanel` 这一壳层，再加 `StreamState` 数据模型。一旦应用要展示"多阶段流式工作流"，就必须从零写：状态图标、折叠语义、阶段时间线、子任务并行树、工具步骤列表、流式→完成态切换……每一项都踩过坑。**这些坑是通用的，应该收敛到平台。**

---

## 1. 平台组件层缺口（`@meso.ai/ui`）

### 1.1 `<WorkflowTrace>` —— 通用的多阶段工作流可视化

**为什么需要**：所有"AI 完成一个复杂任务"的产品形态都长这样：
```
[用户输入]
 ├─ Stage 1: 理解 / 规划   ── 包含 think-stream + 结构化输出
 ├─ Stage 2: 检索 / 查询   ── 含 N 个并行子任务
 ├─ Stage 3: 处理 / 抓取   ── 含 N 个工具调用
 └─ Stage 4: 生成 / 综合   ── 流式正文输出
```

LitPilot 是 literature review；下一个接入 meso 的应用如果是法律检索、市场调研、数据分析助手，UI 模型完全一样，只是 stage 名变了。

**应提供的 API（草案）**：
```tsx
<WorkflowTrace
  stages={workflow.cards}              // 标准化 stage 数组
  trace={trace}                         // ToolCall / ThinkStream / Extension
  streaming={isLive}
  renderStageBody={(stage) => ...}      // 应用层注入领域特化 body
  renderToolCall={(tool) => ...}        // 应用层注入特殊工具展示
  defaultFoldBehavior="userIntent"      // 见 2.3
/>
```

**LitPilot 自建对应物**：`TurnWorkflowBlock` + `WorkflowCardView`（~400 行 TSX + 250 行 CSS）。

---

### 1.2 `<StatusIcon>` —— 状态图标 design primitive

**为什么需要**：LitPilot 第二轮审查时发现页面上同时存在 **6 种** 不同的"状态符号"：

| 状态 | 散落在代码各处的写法 |
|---|---|
| running | `▸` / `<spinner>` / `·` / `"进行中"` 文字 |
| done | `✓` / `▾` / `<svg checkmark>` / `"完成"` 文字 |
| error | `×` / 红字 / 红边框 |
| pending | `○` / `·` / `▸` / 空 |

每个应用都会经历这个"图标考古"阶段。

**应提供的 API**：
```tsx
<StatusIcon status="running" | "done" | "error" | "pending" | "warning" />
```
支持主题变量、可读 aria-label、统一动画。

**LitPilot 自建对应物**：`StatusIcon.tsx`（48 行 + 30 行 CSS）。

---

### 1.3 `<ProcessTimeline>` —— 带竖轴脊线的时间线容器

**为什么需要**：多 stage 卡片直接堆叠会显得离散；加上一条 1px 竖脊把图标列连起来，"流程感"立刻出来。这是 Claude / ChatGPT 等产品都在用的视觉语言，但实现细节繁琐：
- 脊线 `::before` 定位
- 图标 `z-index` + 背景色遮盖脊线
- gap vs padding 的取舍

**LitPilot 自建对应物**：`.litpilot-turn-log__cards::before` + `.litpilot-wf-card__marker { z-index, background }`（45 行 CSS）。

---

### 1.4 `<ThinkFold>` —— 流式推理折叠

**为什么需要**：所有用了"thinking model"的应用都要展示中间推理：
- 流式中：展开 + 光标动画 + 滚到底
- 阶段结束：自动折叠（节约纵向空间）
- 用户手动展开/折叠：意图必须被尊重，不被系统状态覆盖
- streaming → done 的瞬间不能"内容刷一下"（这是 LitPilot 第三轮审查的核心痛点 #5）

**应提供的 API**：
```tsx
<ThinkFold
  content={liveContent}
  pinnedContent={frozenSnapshot}        // 解决 streaming→done 闪烁
  streaming={phaseStreaming}
  turnStreaming={turnStreaming}         // 区分阶段流与整轮流，见 2.4
/>
```

**LitPilot 自建对应物**：`LitPilotThinkFold.tsx`（92 行）+ 反复迭代 3 轮才稳定的折叠/展开语义。

---

### 1.5 `<LogLine>` —— inline-chevron 可展开行

**为什么需要**：流式日志里大量"短文字 + 可选返回内容"行。把"查看返回内容"做成独立浮动按钮会和文字抢视觉焦点；把 `▸` / `▾` chevron 直接附在文字后面、整行可点击，是 Claude Code 的成熟模式（截图已经证明用户认可）。

**应提供的 API**：
```tsx
<LogLine
  status="running" | "done" | "error" | "pending"
  primary="检索学术文献"
  outcome="找到 13 篇文献 · 30s"
  detail={rawJsonString}                // 可选；提供则启用 inline chevron
/>
```

**LitPilot 自建对应物**：`LitPilotToolStep.tsx` + `WorkflowInlineLogLine`（合计 80 行 + `__text--toggle` / `__chevron` CSS）。

---

### 1.6 Design tokens —— 字号 / 字重 / 间距 / 状态色

**为什么需要**：LitPilot 第二轮审查发现字号 `12 / 13 / 14 / 15px` 在同一界面无规律混用，间距 `4 / 6 / 8 / 10 / 12px` 全是 magic number。最后建立了 `--lp-fs-*` / `--lp-fw-*` / `--lp-space-*` / `--lp-status-*` 一整套 token。

**这是 meso 平台层应该提供的**，应用层只做主题扩展，不能每个应用各造一套。

**草案**：
```css
:root {
  /* Type scale */
  --meso-fs-caption: 12px;
  --meso-fs-body:    14px;
  --meso-fs-title:   15px;
  --meso-fs-section: 18px;

  /* Spacing scale (4px base) */
  --meso-space-1: 4px;   /* 1× */
  --meso-space-2: 8px;
  --meso-space-3: 12px;
  --meso-space-4: 16px;
  --meso-space-6: 24px;
  --meso-indent: 16px;   /* layered indent unit */

  /* Status colors (theme-aware) */
  --meso-status-running: ...;
  --meso-status-done:    ...;
  --meso-status-pending: ...;
  --meso-status-error:   ...;
}
```

---

## 2. 行为模式 / 平台约定层

### 2.1 SSE 断连处理链 ★★★★★

**为什么紧急**：LitPilot 在 PR #7 之前会出现 backend 跑完整个 LLM pipeline 但 frontend 早就关掉了浏览器 tab 的情况——浪费 token、占用 worker。

**Backend 必须**：
```python
async def stream_handler(request: Request) -> StreamingResponse:
    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            await cleanup()
            raise
    return StreamingResponse(gen())
```

**Frontend 必须**：
- Next.js catch-all proxy 透传 `AbortSignal`
- 上游 fetch 加 `signal: req.signal`
- 捕获 `AbortError` → 返回 499
- SSE 读取端加 inactivity watchdog（建议 120s）

**Meso 平台应做**：
- 提供 `useMesoSSEStream` hook，内置 watchdog + AbortSignal 透传
- 后端提供 `@meso_sse_handler` 装饰器，封装 disconnect 检测 + cleanup

---

### 2.2 FastAPI 路由 async/sync 规范

**为什么需要**：FastAPI 的"sync def 自动调度到 threadpool / async def 直接占用 event loop"是著名陷阱。LitPilot PR #7 修了 6 个文件的 `async def` 滥用——所有人都会踩。

**Meso 平台应做**：
- 提供项目脚手架 / cookiecutter 模板，含正确的路由分类
- 提供 lint rule：`async def` 路由内禁止出现 `requests.get` / `time.sleep` 等阻塞调用
- 工具函数 `meso.async_io.to_thread()` 封装常用阻塞 I/O

---

### 2.3 `userIntent: boolean | null` 折叠状态模式

**为什么需要**：可折叠组件的开/关受三股力量影响：
1. 系统默认（基于卡片状态、流式状态）
2. 用户主动点击
3. 流式过程中的自动展开

LitPilot 在第二轮审查时发现：用户点开了一张已完成的卡片，下一个事件到来又自动收起，体验崩坏。

**正确模式**：
```ts
const [userIntent, setUserIntent] = useState<boolean | null>(null);
//                                                  ^^^^
//                                  null = 跟随系统；true/false = 锁定意图

const systemOpen = computedFromStateAndProps();
const open = userIntent !== null ? userIntent : systemOpen;

useEffect(() => {
  // 流结束后清意图，让下一轮回到系统默认
  if (!streaming) setUserIntent(null);
}, [streaming]);
```

**Meso 平台应做**：把这个模式封装为 `useFoldState({ system, streaming })` hook，所有可折叠组件统一使用。

---

### 2.4 阶段流 vs 整轮流：`streaming` + `turnStreaming` 双层

**为什么需要**：流式 turn 内部有多个 stage，每个 stage 自己也有 streaming → done 的转换。组件需要同时知道：
- 当前 stage 是否在流（用于 spinner / cursor）
- 整个 turn 是否还在流（用于"turn 结束时统一折叠所有子组件"）

LitPilot 通过 `streaming` + `turnStreaming` 两个 prop 解决。如果只有一个 flag，要么 stage done 时该折叠的没折叠（turn 还在跑），要么 turn done 时还在闪 cursor（stage 已结束）。

**Meso 平台应做**：把"phase streaming"作为 `StreamState` 的一等公民字段，不要让每个应用自己 derive。

---

### 2.5 流式 → 完成态 渲染路径必须同源

**为什么需要**（LitPilot 第三轮审查 #5 的核心修复）：
LitPilot 之前的 bug 是：
- 流式中：内容在 `<ThinkFold>` 里渲染
- 完成时：同一份内容**又**被写入 `<div class="body-text">` 渲染一遍

stage 结束的瞬间用户能看到一次明显的"刷新"，加上内容容器变了、间距字号都变。

**平台原则应该写进文档**：
> Streaming 与 done 必须共用同一渲染路径。done 不是"换组件"，是"同组件的不同 prop 状态"。

---

### 2.6 Proxy 流式转发 + AbortSignal 透传

**为什么需要**：Next.js / 任何 BFF 层做 SSE 代理时，常见错误：
- 用 `await upstream.arrayBuffer()` 转发 → 完全失去流式
- 不透传 `req.signal` → 客户端断开后上游继续跑

**Meso 平台应做**：提供 `mesoProxyStream(req, upstreamUrl)` 工具函数：
- 透传 body / headers / AbortSignal
- 返回 streaming `Response`
- 内置 timeout / combineSignals

---

## 3. 类型 / 数据模型层（`@meso.ai/types` / `StreamState`）

### 3.1 `StreamState` 应原生模型化"阶段"

**现状**：LitPilot 通过 `extensionLog` 里硬拼的 `literature_phase_think` / `literature_progress` / `literature_brief_assessment` 等扩展事件，在前端 derive 出 stage 模型。每个应用都要自己写 derive 逻辑，复杂且易错。

**建议增字段**：
```ts
interface StreamState {
  // ... existing
  phases: Array<{
    id: string;
    name: string;
    state: 'pending' | 'running' | 'done' | 'error';
    thinkContent?: string;        // 阶段独立的 think stream
    pinnedThink?: string;          // done 时下发的快照
    body?: string;                  // 阶段结构化输出
    startedAt?: number;
    endedAt?: number;
  }>;
}
```

后端要做的工作是：发 phase 边界事件，前端自然得到结构化数据。

---

### 3.2 Tool call meta 必须可携带"归属 ID"

**为什么需要**：LitPilot 第二、三轮审查反复出现"工具调用孤魂"问题：检索某子主题的 `OpenAlex` 工具步骤显示在子主题列表外。根因是前端只能靠 tool call title 里的 `(1/4)` 文本去推断"属于第 1 个子主题"——脆弱。

**应增字段**：
```ts
interface ToolCallState {
  // ... existing
  groupId?: string;     // 比如 "subtopic-ai-mom"
  groupKind?: string;   // 比如 "subtopic"
}
```

前端按 `groupId` 路由 tool step 到对应 UI 容器，文本解析时代结束。

---

### 3.3 Stage 名称应有 canonical schema

**为什么需要**：LitPilot 第三轮审查发现 "Brief 评估" 字符串散落在后端，前端想改文案得改后端、要兼容旧数据。Stage canonical key 应该和展示文案分离。

**应增结构**：
```ts
enum CanonicalStage {
  UNDERSTAND = 'understand',
  BRIEF      = 'brief',
  SEARCH     = 'search',
  FETCH      = 'fetch',
  // ...
}

interface PhaseEvent {
  stage: CanonicalStage;        // 后端只发 key
  displayName?: string;          // 可选 i18n 覆盖
}
```

应用层做 `key → 显示文案` 的映射，文案改动不再要求后端发版。

---

## 4. 工具 / 脚手架层

### 4.1 项目脚手架（cookiecutter / npx create-meso-app）

含：
- `error.tsx` / `not-found.tsx` Next.js error boundaries
- SSE proxy template
- `useBatchedSSEStream` with watchdog
- 后端 FastAPI lifespan template
- 设计 token base

### 4.2 ESLint plugin `@meso/eslint-plugin`

规则：
- `no-blocking-in-async-route`：禁止 `async def` 路由里出现 sync I/O
- `prefer-meso-status-icon`：禁止用 ad-hoc symbol 当状态符
- `meso-fold-state-pattern`：检测可折叠组件未使用 `userIntent` 模式

### 4.3 后端 `meso-py` SDK

- `@meso_sse_handler` 装饰器
- `meso.async_io.to_thread()` 封装
- `meso.stream.PhaseEvent` 类型化的阶段事件发射器

---

## 5. 优先级建议

| 优先级 | 项 | 工作量 | 受益面 |
|---|---|---|---|
| ★★★★★ | 1.2 StatusIcon | XS | 所有 meso 应用 |
| ★★★★★ | 1.6 Design tokens | S | 所有 meso 应用 |
| ★★★★★ | 2.1 SSE 断连处理 | M | 所有流式应用 |
| ★★★★★ | 2.2 FastAPI async/sync 规范 | M（文档+lint） | 所有后端 |
| ★★★★ | 1.5 LogLine | S | 所有有"日志/工具调用"展示的应用 |
| ★★★★ | 2.3 userIntent 折叠 | XS | 所有有折叠组件的应用 |
| ★★★★ | 3.1 StreamState 阶段化 | L | 所有多阶段任务应用 |
| ★★★★ | 2.5 streaming↔done 同源 | XS（文档约定） | 所有流式 UI |
| ★★★ | 1.4 ThinkFold | M | 用 thinking model 的应用 |
| ★★★ | 3.2 Tool call groupId | S（前后端联动） | 子任务并行模式 |
| ★★★ | 1.3 ProcessTimeline | M | 工作流类应用 |
| ★★★ | 1.1 WorkflowTrace | L | 工作流类应用（最高价值但最大工程量） |
| ★★ | 3.3 Canonical stage | M | 多语言/迭代频繁的应用 |
| ★★ | 4.x 脚手架 / lint / SDK | M | 新接入应用 |

---

## 6. LitPilot 可贡献的代码

如果 meso 团队需要，LitPilot 可以贡献以下文件作为起点（已经在生产中跑过 3 轮迭代）：

| 文件 | 内容 |
|---|---|
| `StatusIcon.tsx` | 1.2 的完整实现 |
| `LitPilotThinkFold.tsx` | 1.4 的实现 + `userIntent` 模式 |
| `LitPilotToolStep.tsx` | 1.5 的实现 |
| `WorkflowCardView.tsx` | 1.1 的雏形 |
| `useBatchedSSEStream.ts` + watchdog | 2.1 的前端实现 |
| `litpilot-brand.css` token 块 | 1.6 的草案 |
| Next.js `[...path]/route.ts` proxy | 2.6 的实现 |

---

## 附录 A：LitPilot 三轮 UI 审查的核心教训

1. **状态符号必须先统一**（StatusIcon），不然后续所有"哪里在跑"的视觉判断都会乱。
2. **设计 token 是 prerequisite**，不是 nice-to-have——没有 token，每次微调都是手术。
3. **折叠状态要分清"系统意图"和"用户意图"**，否则交互必然崩。
4. **streaming → done 渲染路径必须同源**——这是用户感知"卡顿/刷新"的最大来源。
5. **timeline 脊线让"流程感"变 obvious**，没有脊线的卡片堆叠永远显得离散。
6. **后端流事件粒度决定前端能不能做出好 UX**——`extensionLog` 兜底可以，但 `phases` 一等公民才是终态。

---

## 附录 B：参考实现链接

- 路由健壮性整改：LitPilot PR #7
- 流式 UI 重设计（Phases 1–4）：LitPilot PR #8
- 流式 → 完成态渲染统一：LitPilot PR #9
- 设计审查迭代记录：本文档作者与 Claude Code 的三轮对话

---

**联系方式**：jacer.huang@gmail.com / LitPilot 团队
