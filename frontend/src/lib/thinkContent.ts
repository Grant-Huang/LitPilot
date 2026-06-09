/** 与后端 think_stream 中系统注记标记一致 */
export const THINK_SYS_START = "⟦sys⟧";
export const THINK_SYS_END = "⟦/sys⟧";

export type ThinkSegment = {
  kind: "model" | "system";
  text: string;
};

export function parseThinkSegments(content: string): ThinkSegment[] {
  const raw = content || "";
  if (!raw.includes(THINK_SYS_START)) {
    // 即便没有 ⟦sys⟧ 标记，文本里仍可能含 backend 发送过的另两种 sys 变体
    // （【sys】或 [sys]），同样要 strip——否则它们会作为字面字符出现在 UI。
    const stripped = _strip_markers(raw);
    return stripped ? [{ kind: "model", text: stripped }] : [];
  }
  const segments: ThinkSegment[] = [];
  let i = 0;
  while (i < raw.length) {
    const start = raw.indexOf(THINK_SYS_START, i);
    if (start === -1) {
      const tail = raw.slice(i);
      if (tail.trim()) segments.push({ kind: "model", text: _strip_markers(tail) });
      break;
    }
    if (start > i) {
      const mid = raw.slice(i, start);
      if (mid.trim()) segments.push({ kind: "model", text: _strip_markers(mid) });
    }
    const end = raw.indexOf(THINK_SYS_END, start + THINK_SYS_START.length);
    if (end === -1) {
      const rest = raw.slice(start + THINK_SYS_START.length);
      if (rest.trim()) segments.push({ kind: "system", text: _strip_markers(rest) });
      break;
    }
    const sysText = raw.slice(start + THINK_SYS_START.length, end);
    if (sysText.trim()) segments.push({ kind: "system", text: _strip_markers(sysText) });
    i = end + THINK_SYS_END.length;
  }
  return segments;
}

/** Strip any residual structural markers from extracted segment text.
 *  后端历史上发送过两种 sys 标记：⟦sys⟧（数学方括号）与 【sys】（中文方括号）/[sys]
 *  （ASCII）。解析时都要兜底剥离，否则它们会作为字面字符出现在 UI 里（round 3 审查 #1）。 */
function _strip_markers(t: string): string {
  return t
    .replace(new RegExp(THINK_SYS_START, "g"), "")
    .replace(new RegExp(THINK_SYS_END, "g"), "")
    .replace(/【\/?sys】/g, "")
    .replace(/\[\/?sys\]/g, "")
    .trim();
}

/** 把单条 model 段按中文枚举词（其一/其二/.../首先/其次/再者/最后/核心挑战）切分成多段，
 *  让长 block 在排版上有自然的小标题分隔（round 3 审查 #G）。后端如果直接发 markdown
 *  其实更好，但在前端兜底拆分能立刻改善阅读体验。 */
const ENUM_SPLIT_RE = /(?=其[一二三四五六七八九十]、?|首先[，,]|其次[，,]|再者[，,]|最后[，,]|核心挑战)/g;

export function splitModelByEnum(text: string): string[] {
  if (!text || !ENUM_SPLIT_RE.test(text)) return [text];
  // RegExp /g state needs reset after .test()
  ENUM_SPLIT_RE.lastIndex = 0;
  const parts = text.split(ENUM_SPLIT_RE).map((s) => s.trim()).filter(Boolean);
  return parts.length > 1 ? parts : [text];
}

/** 把"瞬时状态 sys 段"过滤掉：sys 段是 backend 用来告诉用户"正在做什么"的 live hint，
 *  一旦其后已经产生了正式 model 输出，前面的 sys 段就过期了，应该不再显示。
 *  只保留最末尾、还没有被 model 段覆盖的那条 sys hint（round 3 审查 #1）。 */
export function dropStaleSysSegments(segments: ThinkSegment[]): ThinkSegment[] {
  const result: ThinkSegment[] = [];
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    if (seg.kind === "system") {
      const hasModelAfter = segments
        .slice(i + 1)
        .some((s) => s.kind === "model" && s.text.trim());
      if (hasModelAfter) continue;
    }
    result.push(seg);
  }
  return result;
}
