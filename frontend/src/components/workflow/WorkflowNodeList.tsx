"use client";

import type { WorkflowGraphJson, NodeStatus } from "@/lib/workflowGraph";

const STATUS_LABEL: Record<NodeStatus, string> = {
  pending: "待执行",
  active: "进行中",
  done: "已完成",
  skipped: "跳过",
  error: "失败",
};

type Props = { graph: WorkflowGraphJson };

export function WorkflowNodeList({ graph }: Props) {
  return (
    <ol className="stock-wf-list">
      {graph.nodes.map((n) => (
        <li
          key={n.id}
          className={`stock-wf-list__item stock-wf-list__item--${n.status}`}
        >
          <span className="stock-wf-list__label">{n.label}</span>
          <span className="stock-wf-list__status">{STATUS_LABEL[n.status]}</span>
          {n.description ? (
            <span className="stock-wf-list__desc">{n.description}</span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
