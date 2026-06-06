"use client";

import { LoadingOutlined } from "@ant-design/icons";
import { Spin } from "antd";
import { useLiteratureTaskOptional } from "@/contexts/LiteratureTaskContext";
import { useAppNavigation } from "@/contexts/AppNavigationContext";
import { useChatSession } from "@/contexts/ChatSessionContext";
import { persistActiveSession } from "@/lib/sessionStorage";
import { isRunningTaskStatus, isTerminalTaskStatus } from "@/lib/taskTypes";

export function SidebarTaskBadge() {
  const taskCtx = useLiteratureTaskOptional();
  const { navigate } = useAppNavigation();
  const { handleSelectSession } = useChatSession();
  const task = taskCtx?.activeTask;

  if (!task) return null;

  const goChat = () => {
    navigate("/chat");
    if (task.sessionId) {
      persistActiveSession(task.sessionId);
      void handleSelectSession(task.sessionId);
    }
  };

  const onCancel = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    void taskCtx?.cancelTask();
  };

  const onDismiss = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    taskCtx?.clearTask();
  };

  if (isRunningTaskStatus(task.status)) {
    return (
      <button
        type="button"
        className="litpilot-task-badge litpilot-task-badge--running"
        title="综述进行中，点击回到会话"
        onClick={goChat}
      >
        <Spin indicator={<LoadingOutlined spin />} size="small" />
        <span className="litpilot-task-badge__label">{task.progress}%</span>
        <span
          role="button"
          tabIndex={0}
          className="litpilot-task-badge__cancel"
          title="中止综述"
          onClick={onCancel}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onCancel(e as unknown as React.MouseEvent);
          }}
        >
          ✕
        </span>
      </button>
    );
  }

  if (task.status === "completed") {
    return (
      <button
        type="button"
        className="litpilot-task-badge litpilot-task-badge--done"
        title="综述已完成"
        onClick={goChat}
      >
        <span className="litpilot-task-badge__label">✓ 完成</span>
        <span
          role="button"
          tabIndex={0}
          className="litpilot-task-badge__cancel"
          title="关闭"
          onClick={onDismiss}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onDismiss(e as unknown as React.MouseEvent);
          }}
        >
          ✕
        </span>
      </button>
    );
  }

  if (task.status === "failed") {
    return (
      <button
        type="button"
        className="litpilot-task-badge litpilot-task-badge--failed"
        title={task.error || "综述失败，点击查看"}
        onClick={goChat}
      >
        <span className="litpilot-task-badge__label">⚠ 失败</span>
        <span
          role="button"
          tabIndex={0}
          className="litpilot-task-badge__cancel"
          title="关闭"
          onClick={onDismiss}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onDismiss(e as unknown as React.MouseEvent);
          }}
        >
          ✕
        </span>
      </button>
    );
  }

  if (isTerminalTaskStatus(task.status)) return null;
  return null;
}
