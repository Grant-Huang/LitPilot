"use client";

import { useMemo } from "react";
import dagre from "@dagrejs/dagre";
import type { WorkflowGraphJson, NodeStatus } from "@/lib/workflowGraph";

const NODE_W = 108;
const NODE_H = 32;
const FONT_SIZE = 11;

const STATUS_COLOR: Record<NodeStatus, string> = {
  pending: "#9aa89e",
  active: "#3d6b4f",
  done: "#527c5e",
  skipped: "#b8c4bc",
  error: "#c45c5c",
};

function layoutGraph(graph: WorkflowGraphJson) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 20, ranksep: 28, marginx: 12, marginy: 12 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of graph.nodes) {
    g.setNode(n.id, { width: NODE_W, height: NODE_H });
  }
  for (const e of graph.edges) {
    g.setEdge(e.source, e.target);
  }
  dagre.layout(g);
  const nodes = graph.nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      label: n.label,
      status: n.status,
      x: pos.x - NODE_W / 2,
      y: pos.y - NODE_H / 2,
    };
  });
  const edges = graph.edges.map((e) => ({
    id: e.id,
    points: g.edge(e.source, e.target).points as { x: number; y: number }[],
  }));
  return {
    nodes,
    edges,
    width: (g.graph().width ?? 320) + 32,
    height: (g.graph().height ?? 240) + 32,
  };
}

type Props = { graph: WorkflowGraphJson };

export function WorkflowGraphView({ graph }: Props) {
  const { nodes, edges, width, height } = useMemo(
    () => layoutGraph(graph),
    [graph],
  );
  return (
    <svg
      className="stock-wf-graph"
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role="img"
      aria-label={graph.title}
    >
      {edges.map((e) => (
        <polyline
          key={e.id}
          fill="none"
          stroke="#c5d0c8"
          strokeWidth={1.5}
          points={e.points.map((p) => `${p.x},${p.y}`).join(" ")}
        />
      ))}
      {nodes.map((n) => (
        <g key={n.id} transform={`translate(${n.x}, ${n.y})`}>
          <rect
            width={NODE_W}
            height={NODE_H}
            rx={6}
            fill="#fff"
            stroke={STATUS_COLOR[n.status]}
            strokeWidth={n.status === "active" ? 2 : 1}
          />
          <text
            x={NODE_W / 2}
            y={NODE_H / 2 + 1}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={FONT_SIZE}
            fill="var(--color-text-secondary, #4a574e)"
          >
            {n.label}
          </text>
        </g>
      ))}
    </svg>
  );
}
