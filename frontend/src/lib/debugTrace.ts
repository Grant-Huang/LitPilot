/**
 * [3-layer trace] 客户端环形缓冲：聚合每个 SSE 事件的 persist/yield/recv 三个时间戳。
 *
 * 调试用，可一键删除。
 */
export type DebugTraceRow = {
  seq: number;
  type: string;
  label: string;
  persistMs: number | null;
  yieldMs: number | null;
  recvMs: number;
};

const MAX_ROWS = 200;

let rows: DebugTraceRow[] = [];
let nextSeq = 0;
const listeners = new Set<() => void>();

function notify() {
  for (const fn of listeners) fn();
}

function shortLabelFor(type: string, payload: unknown): string {
  const p = (payload ?? {}) as Record<string, unknown>;
  switch (type) {
    case "stage":
      return `${String(p.name ?? "")}/${String(p.state ?? "")}`;
    case "extension": {
      const name = String(p.name ?? "");
      const data = (p.data ?? {}) as Record<string, unknown>;
      const intent = data.intent ? `:${String(data.intent)}` : "";
      const stage = data.stage ? `:${String(data.stage)}` : "";
      const detail =
        typeof data.detail === "string"
          ? `:${data.detail.slice(0, 18)}`
          : "";
      return `${name}${intent}${stage}${detail}`;
    }
    case "tool_call":
      return String(p.name ?? "");
    case "text":
    case "think":
    case "artifact": {
      const delta = typeof p.delta === "string" ? p.delta : "";
      return `Δ=${delta.length}`;
    }
    default:
      return "";
  }
}

export function pushDebugTrace(event: {
  type: string;
  payload?: unknown;
  _trace?: { persist_ms?: number; yield_ms?: number };
}): void {
  nextSeq += 1;
  const row: DebugTraceRow = {
    seq: nextSeq,
    type: event.type,
    label: shortLabelFor(event.type, event.payload),
    persistMs: event._trace?.persist_ms ?? null,
    yieldMs: event._trace?.yield_ms ?? null,
    recvMs: Date.now(),
  };
  rows = rows.length >= MAX_ROWS ? [...rows.slice(1), row] : [...rows, row];
  notify();
}

export function clearDebugTrace(): void {
  rows = [];
  nextSeq = 0;
  notify();
}

export function getDebugTrace(): DebugTraceRow[] {
  return rows;
}

export function subscribeDebugTrace(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}
