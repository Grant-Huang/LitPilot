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
    return raw.trim() ? [{ kind: "model", text: raw }] : [];
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

/** Strip any residual structural markers from extracted segment text. */
function _strip_markers(t: string): string {
  return t
    .replace(new RegExp(THINK_SYS_START, "g"), "")
    .replace(new RegExp(THINK_SYS_END, "g"), "")
    .trim();
}
