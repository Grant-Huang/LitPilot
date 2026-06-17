"use client";

import { useSyncExternalStore, useMemo, useState } from "react";
import {
  getDebugTrace,
  subscribeDebugTrace,
  type DebugTraceRow,
} from "@/lib/debugTrace";

function fmt(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(0)}`;
}

function fmtDelta(a: number | null, b: number | null): string {
  if (a == null || b == null) return "—";
  return `${(a - b).toFixed(0)}`;
}

export function DebugTracePanel() {
  const [open, setOpen] = useState(true);
  const rows = useSyncExternalStore<DebugTraceRow[]>(
    subscribeDebugTrace,
    getDebugTrace,
    () => [],
  );

  const baseline = useMemo(() => {
    for (const r of rows) {
      if (r.persistMs != null) return r.persistMs;
    }
    return rows[0]?.recvMs ?? Date.now();
  }, [rows]);

  if (rows.length === 0) return null;

  return (
    <div
      style={{
        marginTop: 8,
        padding: 10,
        border: "1px solid #d0d7de",
        borderRadius: 6,
        background: "#fafbfc",
        fontFamily:
          "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        fontSize: 11,
        color: "#24292f",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 6,
        }}
      >
        <strong style={{ fontSize: 11 }}>3-layer trace</strong>
        <span style={{ color: "#57606a" }}>events: {rows.length}</span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          style={{
            marginLeft: "auto",
            fontSize: 11,
            padding: "2px 6px",
            border: "1px solid #d0d7de",
            background: "#fff",
            borderRadius: 4,
            cursor: "pointer",
          }}
        >
          {open ? "collapse" : "expand"}
        </button>
      </div>
      {open ? (
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              borderCollapse: "collapse",
              width: "100%",
              fontSize: 11,
            }}
          >
            <thead>
              <tr style={{ background: "#eef2f5", textAlign: "right" }}>
                <th style={th}>#</th>
                <th style={{ ...th, textAlign: "left" }}>type / label</th>
                <th style={th} title="persist_ms - baseline">t_persist</th>
                <th style={th} title="yield_ms - persist_ms (后端 batch/poll 延迟)">
                  Δp→y
                </th>
                <th style={th} title="recv_ms - yield_ms (Next.js 代理 + 网络)">
                  Δy→r
                </th>
                <th style={th} title="recv_ms - persist_ms (端到端)">
                  Δp→r
                </th>
                <th style={th} title="自上条事件落盘后的间隔（找黑洞）">
                  gap_persist
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const prev = i > 0 ? rows[i - 1] : null;
                const tp =
                  r.persistMs != null ? r.persistMs - baseline : null;
                const gap =
                  prev && r.persistMs != null && prev.persistMs != null
                    ? r.persistMs - prev.persistMs
                    : null;
                const big = gap != null && gap >= 500;
                return (
                  <tr
                    key={r.seq}
                    style={{
                      borderTop: "1px solid #eaeef2",
                      background: big ? "#fff5f0" : undefined,
                    }}
                  >
                    <td style={tdRight}>{r.seq}</td>
                    <td style={tdLeft}>
                      <span style={{ fontWeight: 600 }}>{r.type}</span>
                      {r.label ? (
                        <span style={{ color: "#57606a" }}> · {r.label}</span>
                      ) : null}
                    </td>
                    <td style={tdRight}>{fmt(tp)}</td>
                    <td style={tdRight}>{fmtDelta(r.yieldMs, r.persistMs)}</td>
                    <td style={tdRight}>{fmtDelta(r.recvMs, r.yieldMs)}</td>
                    <td style={tdRight}>{fmtDelta(r.recvMs, r.persistMs)}</td>
                    <td
                      style={{
                        ...tdRight,
                        color: big ? "#cf222e" : undefined,
                        fontWeight: big ? 600 : undefined,
                      }}
                    >
                      {gap != null ? gap.toFixed(0) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ marginTop: 6, color: "#57606a", fontSize: 10 }}>
            单位 ms。t_persist 相对首条事件落盘。Δp→y 大 = 后端 batch/poll 滞留；
            Δy→r 大 = Next.js 代理 / 网络缓冲；gap_persist 大 = 后端两条事件之间静默（无声黑洞）。
          </div>
        </div>
      ) : null}
    </div>
  );
}

const th: React.CSSProperties = {
  padding: "4px 8px",
  borderBottom: "1px solid #d0d7de",
  textAlign: "right",
  fontWeight: 600,
};
const tdRight: React.CSSProperties = {
  padding: "3px 8px",
  textAlign: "right",
  whiteSpace: "nowrap",
};
const tdLeft: React.CSSProperties = {
  padding: "3px 8px",
  textAlign: "left",
  whiteSpace: "nowrap",
  maxWidth: 360,
  overflow: "hidden",
  textOverflow: "ellipsis",
};
