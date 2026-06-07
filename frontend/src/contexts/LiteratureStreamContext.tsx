"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { toastError } from "@/lib/toastFeedback";
import { useBatchedSSEStream } from "@/hooks/useBatchedSSEStream";
import { useChatSession } from "@/contexts/ChatSessionContext";
import { useLiteratureTask } from "@/contexts/LiteratureTaskContext";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { collectExecutionTraceFromStream } from "@/lib/executionTrace";
import { handleLiteratureExtensionEvent } from "@/lib/literatureExtensionHandlers";
import { materializeAssistantFromStream } from "@/lib/streamMaterialize";
import { persistActiveSession } from "@/lib/sessionStorage";
import { deriveLiveFieldsFromStream } from "@/lib/turnWorkflow";
import {
  computeLiteratureStreamPhase,
  isLiteratureStreamBusy,
  type LiteratureStreamPhase,
} from "@/lib/literatureStreamPhase";
import { sessionHasAssistantReply } from "@/lib/streamTurnFinalize";
import { sessionsApi } from "@/lib/api";
import { tasksApi } from "@/lib/tasksApi";
import { clearClarificationUnreadTitle } from "@/lib/clarificationTitle";
import {
  isRunningTaskStatus,
  isTerminalTaskStatus,
  mapStatusRow,
} from "@/lib/taskTypes";

type LiteratureStreamContextValue = {
  streamState: ReturnType<typeof useBatchedSSEStream>["state"];
  liveMessages: LitPilotMessage[];
  streamPhase: LiteratureStreamPhase;
  isStreamBusy: boolean;
  send: (
    text: string,
    fetchUrls: string[],
  ) => Promise<void>;
  stop: () => Promise<void>;
};

const LiteratureStreamContext =
  createContext<LiteratureStreamContextValue | null>(null);

function taskStreamUrl(taskId: string, since: number): string {
  return `/api/tasks/${encodeURIComponent(taskId)}/stream?since=${since}`;
}

export function LiteratureStreamProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isChat = pathname === "/chat" || pathname.startsWith("/chat/");
  const {
    activeSessionId,
    messages: storedMessages,
    loadSessions,
    reloadSessionMessages,
    setActiveSessionId,
    clearMessages,
  } = useChatSession();
  const {
    activeTask,
    setActiveTask,
    registerEventSeq,
    refreshFromServer,
    clearTask,
    cancelTask,
  } = useLiteratureTask();

  const streamErrorMsgRef = useRef<string | null>(null);

  const { state: streamState, start, abort, reset } = useBatchedSSEStream(
    "/api/tasks/idle/stream",
    { onError: (msg: string) => { streamErrorMsgRef.current = msg; } },
  );

  const [liveMessages, setLiveMessages] = useState<LitPilotMessage[]>([]);
  const [streamPending, setStreamPending] = useState(false);
  const [streamSettling, setStreamSettling] = useState(false);
  const streamStartedRef = useRef(false);
  const streamFinalizeRef = useRef(false);
  const turnGenerationRef = useRef(0);
  const turnSessionRef = useRef<string | null>(null);
  const streamSessionRef = useRef<string | null>(null);
  const pendingUserTextRef = useRef<string | null>(null);
  const extensionHandledRef = useRef(0);
  const prevActiveSessionRef = useRef<string | null>(null);
  const connectedTaskIdRef = useRef<string | null>(null);
  const reconnectingRef = useRef(false);
  const stopMaterializedRef = useRef(false);

  const streamPhase = useMemo(
    () =>
      computeLiteratureStreamPhase(
        streamState.status,
        streamPending,
        streamSettling,
      ),
    [streamState.status, streamPending, streamSettling],
  );
  const isStreamBusy = isLiteratureStreamBusy(streamPhase);

  const resetStreamLocalState = useCallback(
    (sessionId: string | null = activeSessionId) => {
      streamStartedRef.current = false;
      streamFinalizeRef.current = false;
      turnSessionRef.current = sessionId;
      streamSessionRef.current = sessionId;
      pendingUserTextRef.current = null;
      extensionHandledRef.current = 0;
      connectedTaskIdRef.current = null;
      streamErrorMsgRef.current = null;
      setStreamSettling(false);
      setStreamPending(false);
      setLiveMessages([]);
    },
    [activeSessionId],
  );

  const connectTaskStream = useCallback(
    async (taskId: string, since: number, preserveState: boolean) => {
      if (since === 0) {
        extensionHandledRef.current = 0;
      }
      connectedTaskIdRef.current = taskId;
      streamStartedRef.current = true;
      setStreamPending(false);
      await start({
        url: taskStreamUrl(taskId, since),
        method: "GET",
        preserveState,
        onEventApplied: (_event, index) => {
          registerEventSeq(since + index);
        },
      });
    },
    [registerEventSeq, start],
  );

  const streamDone = streamState.status === "done";
  const streamError = streamState.status === "error";

  useEffect(() => {
    if (streamState.status === "streaming") {
      setStreamPending(false);
    }
  }, [streamState.status]);

  useEffect(() => {
    const prev = prevActiveSessionRef.current;
    prevActiveSessionRef.current = activeSessionId;
    if (prev === activeSessionId) return;

    if (streamPhase === "streaming") {
      abort();
    }
    reset();
    resetStreamLocalState(activeSessionId);
  }, [
    activeSessionId,
    streamPhase,
    abort,
    reset,
    resetStreamLocalState,
  ]);

  useEffect(() => {
    return () => {
      abort();
    };
  }, [abort]);

  useEffect(() => {
    if (isChat) return;
    if (streamPhase === "streaming") {
      abort();
    }
  }, [isChat, streamPhase, abort]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await refreshFromServer();
      if (cancelled || !activeSessionId) return;
      await reloadSessionMessages(activeSessionId);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only chat rehydrate
  }, []);

  useEffect(() => {
    if (activeTask?.status !== "cancelled") return;
    abort();
    reset();
    streamStartedRef.current = false;
    connectedTaskIdRef.current = null;
    streamFinalizeRef.current = false;
    setStreamPending(false);
    setStreamSettling(false);
    if (!stopMaterializedRef.current) {
      resetStreamLocalState(activeSessionId);
    } else {
      pendingUserTextRef.current = null;
      stopMaterializedRef.current = false;
    }
    clearTask();
  }, [
    activeTask?.status,
    abort,
    reset,
    resetStreamLocalState,
    activeSessionId,
    clearTask,
  ]);

  useEffect(() => {
    if (!isChat || !activeTask) return;
    if (activeTask.sessionId !== activeSessionId) return;

    if (
      isTerminalTaskStatus(activeTask.status) &&
      streamPhase === "idle"
    ) {
      void reloadSessionMessages(activeTask.sessionId);
      return;
    }

    if (!isRunningTaskStatus(activeTask.status)) return;
    if (streamPhase === "streaming" || reconnectingRef.current) return;
    if (
      connectedTaskIdRef.current === activeTask.taskId &&
      streamStartedRef.current
    ) {
      return;
    }

    reconnectingRef.current = true;
    void connectTaskStream(activeTask.taskId, 0, false)
      .catch((e: unknown) => {
        if (e instanceof Error && e.name === "AbortError") return;
        const msg = e instanceof Error ? e.message : String(e);
        toastError(msg || "重连任务流失败");
      })
      .finally(() => {
        reconnectingRef.current = false;
      });
  }, [
    isChat,
    activeTask,
    activeSessionId,
    streamPhase,
    connectTaskStream,
    reloadSessionMessages,
  ]);

  useEffect(() => {
    if (!streamStartedRef.current || !(streamDone || streamError)) return;
    if (streamFinalizeRef.current) return;
    streamFinalizeRef.current = true;
    setStreamSettling(true);

    const turnGen = turnGenerationRef.current;
    const sid =
      streamSessionRef.current || turnSessionRef.current || activeSessionId;
    const pendingUser = pendingUserTextRef.current;
    const { chatText } = deriveLiveFieldsFromStream(streamState);
    const trace = collectExecutionTraceFromStream(streamState);
    const hasTrace =
      trace.stages.length > 0 ||
      trace.tools.length > 0 ||
      trace.workflows.length > 0 ||
      Boolean(trace.thinkContent);

    setLiveMessages((prev) => {
      const users = prev.filter((m) => m.role === "user");
      const baseUsers =
        users.length > 0
          ? users
          : pendingUser
            ? [
                {
                  id: `pending-user-${Date.now()}`,
                  role: "user" as const,
                  content: pendingUser,
                },
              ]
            : [];
      const placeholderContent =
        chatText.trim() ||
        (streamError
          ? streamErrorMsgRef.current
            ? `请求失败：${streamErrorMsgRef.current}`
            : "请求失败，请重试。"
          : "（正在保存回答…）");
      return [
        ...baseUsers,
        {
          id: `pending-assistant-${Date.now()}`,
          role: "assistant" as const,
          content: placeholderContent,
          extras: hasTrace
            ? {
                executionTrace: trace,
                thinkContent: trace.thinkContent,
              }
            : undefined,
        },
      ];
    });

    void (async () => {
      try {
        await loadSessions();
        if (sid) {
          await reloadSessionMessages(sid, { pendingUserText: pendingUser });
        }
        await refreshFromServer();
      } finally {
        if (turnGenerationRef.current !== turnGen) return;
        reset();
        streamStartedRef.current = false;
        turnSessionRef.current = null;
        streamSessionRef.current = null;
        pendingUserTextRef.current = null;
        streamFinalizeRef.current = false;
        connectedTaskIdRef.current = null;
        setStreamSettling(false);
        setLiveMessages([]);
      }
    })();
  }, [
    streamDone,
    streamError,
    streamState,
    reset,
    loadSessions,
    activeSessionId,
    reloadSessionMessages,
    refreshFromServer,
  ]);

  useEffect(() => {
    const log = streamState.extensionLog;
    const extCtx = {
      isChat,
      setActiveSessionId,
      loadSessions,
      persistActiveSession,
    };
    for (let i = extensionHandledRef.current; i < log.length; i += 1) {
      const ext = log[i];
      const name = ext.payload.name;
      const data = (ext.payload.data ?? {}) as Record<string, unknown>;
      if (name === "session" && streamStartedRef.current) {
        const sid = data.session_id;
        if (typeof sid === "string" && sid) {
          streamSessionRef.current = sid;
          turnSessionRef.current = sid;
        }
      }
      handleLiteratureExtensionEvent(name, data, extCtx);
    }
    extensionHandledRef.current = log.length;
  }, [streamState.extensionLog, isChat, setActiveSessionId, loadSessions]);

  useEffect(() => {
    const pending = pendingUserTextRef.current;
    if (!pending || streamSettling) return;
    const persisted = storedMessages.some(
      (m) => m.role === "user" && m.content === pending,
    );
    if (!persisted) return;
    if (sessionHasAssistantReply(storedMessages, pending)) {
      pendingUserTextRef.current = null;
      setLiveMessages([]);
      return;
    }
    setLiveMessages((prev) => {
      if (prev.some((m) => m.role === "assistant")) return prev;
      return prev.filter((m) => !(m.role === "user" && m.content === pending));
    });
  }, [storedMessages, streamSettling]);

  useEffect(() => {
    if (isStreamBusy) return;
    if (turnSessionRef.current && turnSessionRef.current !== activeSessionId) {
      setLiveMessages([]);
    }
  }, [activeSessionId, isStreamBusy]);

  const send = useCallback(
    async (
      text: string,
      fetchUrls: string[],
    ) => {
      const trimmed = text.trim();
      if (!trimmed || isStreamBusy) return;

      let sessionId = activeSessionId;
      if (!sessionId) {
        const meta = await sessionsApi.create();
        sessionId = meta.id;
        setActiveSessionId(sessionId);
        persistActiveSession(sessionId);
        clearMessages();
        await loadSessions();
      }

      turnGenerationRef.current += 1;
      streamFinalizeRef.current = false;
      turnSessionRef.current = sessionId;
      streamSessionRef.current = sessionId;
      clearClarificationUnreadTitle();
      pendingUserTextRef.current = trimmed;
      setStreamPending(true);
      setLiveMessages([
        {
          id: `pending-user-${Date.now()}`,
          role: "user",
          content: trimmed,
        },
      ]);
      reset();
      streamStartedRef.current = true;

      try {
        const row = await tasksApi.create({
          message: trimmed,
          session_id: sessionId ?? undefined,
          ...(fetchUrls.length ? { fetch_urls: fetchUrls } : {}),
        });
        const task = {
          ...mapStatusRow(row),
          startedAt: Date.now(),
          lastEventSeq: 0,
          notified: false,
        };
        setActiveTask(task);
        await connectTaskStream(row.task_id, 0, false);
      } catch (e: unknown) {
        if (e instanceof Error && e.name === "AbortError") return;
        const errText = e instanceof Error ? e.message : String(e);
        toastError(errText);
        setLiveMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "assistant",
            content: `错误: ${errText}`,
          },
        ]);
        streamStartedRef.current = false;
        turnSessionRef.current = null;
        streamSessionRef.current = null;
        streamFinalizeRef.current = false;
        connectedTaskIdRef.current = null;
        setStreamSettling(false);
        setStreamPending(false);
        reset();
        clearTask();
      }
    },
    [
      activeSessionId,
      isStreamBusy,
      setActiveSessionId,
      loadSessions,
      clearMessages,
      reset,
      setActiveTask,
      connectTaskStream,
      clearTask,
    ],
  );

  const stop = useCallback(async () => {
    if (!isStreamBusy) return;

    streamFinalizeRef.current = true;
    stopMaterializedRef.current = true;

    const pendingUser = pendingUserTextRef.current;
    const materialized = materializeAssistantFromStream(streamState);

    setLiveMessages((prev) => {
      const users = prev.filter((m) => m.role === "user");
      const baseUsers =
        users.length > 0
          ? users
          : pendingUser
            ? [
                {
                  id: `pending-user-${Date.now()}`,
                  role: "user" as const,
                  content: pendingUser,
                },
              ]
            : [];
      if (materialized) {
        return [...baseUsers, materialized];
      }
      const assistants = prev.filter((m) => m.role === "assistant");
      if (assistants.length > 0) return [...baseUsers, ...assistants];
      const { processText, chatText } = deriveLiveFieldsFromStream(streamState);
      if (
        baseUsers.length > 0 &&
        (processText.trim() ||
          chatText.trim() ||
          streamState.status !== "idle")
      ) {
        const trace = collectExecutionTraceFromStream(streamState);
        const hasTrace =
          trace.stages.length > 0 ||
          trace.tools.length > 0 ||
          trace.workflows.length > 0 ||
          Boolean(trace.thinkContent);
        return [
          ...baseUsers,
          {
            id: `stopped-assistant-${Date.now()}`,
            role: "assistant" as const,
            content: chatText.trim() || "（已停止）",
            extras: hasTrace
              ? {
                  executionTrace: trace,
                  thinkContent: trace.thinkContent,
                }
              : undefined,
          },
        ];
      }
      return prev.length > 0 ? prev : baseUsers;
    });

    pendingUserTextRef.current = null;
    abort();
    reset();
    streamStartedRef.current = false;
    connectedTaskIdRef.current = null;
    setStreamPending(false);
    setStreamSettling(false);

    if (activeTask && isRunningTaskStatus(activeTask.status)) {
      await cancelTask();
    } else {
      stopMaterializedRef.current = false;
      streamFinalizeRef.current = false;
      clearTask();
    }
  }, [
    isStreamBusy,
    streamState,
    abort,
    reset,
    activeTask,
    cancelTask,
    clearTask,
  ]);

  const value = useMemo(
    () => ({
      streamState,
      liveMessages,
      streamPhase,
      isStreamBusy,
      send,
      stop,
    }),
    [streamState, liveMessages, streamPhase, isStreamBusy, send, stop],
  );

  return (
    <LiteratureStreamContext.Provider value={value}>
      {children}
    </LiteratureStreamContext.Provider>
  );
}

export function useLiteratureStream() {
  const ctx = useContext(LiteratureStreamContext);
  if (!ctx) {
    throw new Error("LiteratureStreamProvider required");
  }
  return ctx;
}
