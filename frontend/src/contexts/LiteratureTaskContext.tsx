"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import { tasksApi } from "@/lib/tasksApi";
import {
  readStoredActiveTask,
  writeStoredActiveTask,
} from "@/lib/taskStorage";
import {
  isRunningTaskStatus,
  isTerminalTaskStatus,
  mapStatusRow,
  type ActiveLiteratureTask,
  type LiteratureTaskStatusRow,
} from "@/lib/taskTypes";
import { toastError, toastSuccess } from "@/lib/toastFeedback";

const POLL_INTERVAL_MS = 5_000;

type LiteratureTaskContextValue = {
  activeTask: ActiveLiteratureTask | null;
  setActiveTask: (task: ActiveLiteratureTask | null) => void;
  patchActiveTask: (patch: Partial<ActiveLiteratureTask>) => void;
  registerEventSeq: (seq: number) => void;
  cancelTask: () => Promise<void>;
  clearTask: () => void;
  refreshFromServer: () => Promise<void>;
};

const LiteratureTaskContext = createContext<LiteratureTaskContextValue | null>(
  null,
);

function mergeTaskRow(
  current: ActiveLiteratureTask | null,
  row: LiteratureTaskStatusRow,
): ActiveLiteratureTask {
  const mapped = mapStatusRow(row);
  return {
    ...mapped,
    lastEventSeq: Math.max(current?.lastEventSeq ?? 0, mapped.lastEventSeq),
    startedAt: current?.startedAt ?? mapped.startedAt,
    notified: current?.notified,
  };
}

export function LiteratureTaskProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isChat = pathname === "/chat" || pathname.startsWith("/chat/");
  const [activeTask, setActiveTaskState] = useState<ActiveLiteratureTask | null>(
    null,
  );
  const activeTaskRef = useRef<ActiveLiteratureTask | null>(null);
  activeTaskRef.current = activeTask;

  const persistTask = useCallback((task: ActiveLiteratureTask | null) => {
    setActiveTaskState(task);
    writeStoredActiveTask(task);
  }, []);

  const patchActiveTask = useCallback(
    (patch: Partial<ActiveLiteratureTask>) => {
      const cur = activeTaskRef.current;
      if (!cur) return;
      persistTask({ ...cur, ...patch });
    },
    [persistTask],
  );

  const registerEventSeq = useCallback(
    (seq: number) => {
      const cur = activeTaskRef.current;
      if (!cur || seq <= cur.lastEventSeq) return;
      patchActiveTask({ lastEventSeq: seq });
    },
    [patchActiveTask],
  );

  const clearTask = useCallback(() => {
    persistTask(null);
  }, [persistTask]);

  const refreshFromServer = useCallback(async () => {
    const cur = activeTaskRef.current;
    if (!cur) return;
    try {
      const row = await tasksApi.status(cur.taskId);
      persistTask(mergeTaskRow(cur, row));
    } catch {
      /* silent */
    }
  }, [persistTask]);

  const cancelTask = useCallback(async () => {
    const cur = activeTaskRef.current;
    if (!cur) return;
    try {
      const row = await tasksApi.cancel(cur.taskId);
      persistTask(mergeTaskRow(cur, row));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toastError(msg || "中止任务失败");
    }
  }, [persistTask]);

  useEffect(() => {
    const stored = readStoredActiveTask();
    if (stored) {
      setActiveTaskState(stored);
    }
    void (async () => {
      try {
        const { items } = await tasksApi.active();
        if (!items?.length) {
          if (stored && isTerminalTaskStatus(stored.status)) {
            persistTask(null);
          }
          return;
        }
        const row = items[0];
        persistTask(mergeTaskRow(stored, row));
      } catch {
        /* keep stored snapshot */
      }
    })();
  }, [persistTask]);

  useEffect(() => {
    const task = activeTask;
    if (!task || !isRunningTaskStatus(task.status)) return;

    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      try {
        const row = await tasksApi.status(task.taskId);
        if (cancelled) return;
        const prev = activeTaskRef.current;
        persistTask(mergeTaskRow(prev, row));
      } catch {
        /* ignore */
      }
    };

    void tick();
    const id = window.setInterval(() => void tick(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [activeTask?.taskId, activeTask?.status, persistTask]);

  useEffect(() => {
    const task = activeTask;
    if (!task || task.notified) return;
    if (!isTerminalTaskStatus(task.status)) return;

    if (task.status === "completed") {
      if (!isChat) {
        toastSuccess("综述已完成，点击会话查看");
      }
      patchActiveTask({ notified: true });
      return;
    }
    if (task.status === "failed") {
      if (!isChat) {
        toastError(task.error || "综述生成失败，请回到会话查看");
      }
      patchActiveTask({ notified: true });
    }
  }, [activeTask, isChat, patchActiveTask]);

  const value = useMemo(
    () => ({
      activeTask,
      setActiveTask: persistTask,
      patchActiveTask,
      registerEventSeq,
      cancelTask,
      clearTask,
      refreshFromServer,
    }),
    [
      activeTask,
      persistTask,
      patchActiveTask,
      registerEventSeq,
      cancelTask,
      clearTask,
      refreshFromServer,
    ],
  );

  return (
    <LiteratureTaskContext.Provider value={value}>
      {children}
    </LiteratureTaskContext.Provider>
  );
}

export function useLiteratureTask() {
  const ctx = useContext(LiteratureTaskContext);
  if (!ctx) {
    throw new Error("LiteratureTaskProvider required");
  }
  return ctx;
}

export function useLiteratureTaskOptional() {
  return useContext(LiteratureTaskContext);
}
