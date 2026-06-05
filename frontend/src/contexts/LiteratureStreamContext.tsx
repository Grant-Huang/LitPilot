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
import { useSSEStream } from "@meso.ai/ui";
import { useChatSession } from "@/contexts/ChatSessionContext";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { collectExecutionTraceFromStream } from "@/lib/executionTrace";
import { handleLiteratureExtensionEvent } from "@/lib/literatureExtensionHandlers";
import { persistActiveSession } from "@/lib/sessionStorage";
import {
  ASSISTANT_RELOAD_ATTEMPTS,
  ASSISTANT_RELOAD_BASE_MS,
  sessionHasAssistantReply,
} from "@/lib/streamTurnFinalize";
import { sessionsApi } from "@/lib/api";
import { clearClarificationUnreadTitle } from "@/lib/clarificationTitle";

type LiteratureStreamContextValue = {
  streamState: ReturnType<typeof useSSEStream>["state"];
  liveMessages: LitPilotMessage[];
  streaming: boolean;
  /** 流已结束，正在等待助手消息落库并刷新会话 */
  streamSettling: boolean;
  send: (text: string, fetchUrls: string[]) => Promise<void>;
  abort: () => void;
  resetStreamUi: () => void;
};

const LiteratureStreamContext =
  createContext<LiteratureStreamContextValue | null>(null);

export function LiteratureStreamProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isChat = pathname === "/chat" || pathname.startsWith("/chat/");
  const {
    activeSessionId,
    messages: storedMessages,
    loadSessions,
    handleSelectSession,
    setActiveSessionId,
    clearMessages,
  } = useChatSession();

  const { state: streamState, start, abort, reset } = useSSEStream(
    "/api/chat/literature/execute",
  );

  const [liveMessages, setLiveMessages] = useState<LitPilotMessage[]>([]);
  const [streamSettling, setStreamSettling] = useState(false);
  const streamStartedRef = useRef(false);
  const streamFinalizeRef = useRef(false);
  const turnGenerationRef = useRef(0);
  const turnSessionRef = useRef<string | null>(null);
  /** SSE extension.session 下发的权威 session_id */
  const streamSessionRef = useRef<string | null>(null);
  const pendingUserTextRef = useRef<string | null>(null);
  const extensionHandledRef = useRef(0);

  const streaming = streamState.status === "streaming";
  const streamDone = streamState.status === "done";
  const streamError = streamState.status === "error";

  useEffect(() => {
    if (!streamStartedRef.current || !(streamDone || streamError)) return;
    if (streamFinalizeRef.current) return;
    streamFinalizeRef.current = true;
    setStreamSettling(true);

    const turnGen = turnGenerationRef.current;
    const sid =
      streamSessionRef.current || turnSessionRef.current || activeSessionId;
    const pendingUser = pendingUserTextRef.current;
    const snapshotText = streamState.textContent?.trim() ?? "";
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
        snapshotText ||
        (streamError ? "请求失败，请查看提示或重试。" : "（正在保存回答…）");
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
          for (let attempt = 0; attempt < ASSISTANT_RELOAD_ATTEMPTS; attempt += 1) {
            await handleSelectSession(sid);
            const msgs = await sessionsApi.messages(sid);
            if (sessionHasAssistantReply(msgs, pendingUser)) break;
            await new Promise((resolve) => {
              setTimeout(resolve, ASSISTANT_RELOAD_BASE_MS + attempt * 80);
            });
          }
        }
      } finally {
        if (turnGenerationRef.current !== turnGen) return;
        reset();
        streamStartedRef.current = false;
        turnSessionRef.current = null;
        streamSessionRef.current = null;
        pendingUserTextRef.current = null;
        streamFinalizeRef.current = false;
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
    handleSelectSession,
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
      if (ext.payload.name === "session" && streamStartedRef.current) {
        const sid = (ext.payload.data as Record<string, unknown> | undefined)
          ?.session_id;
        if (typeof sid === "string" && sid) {
          streamSessionRef.current = sid;
          turnSessionRef.current = sid;
        }
      }
      handleLiteratureExtensionEvent(
        ext.payload.name,
        ext.payload.data as Record<string, unknown> | undefined,
        extCtx,
      );
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
    setLiveMessages((prev) =>
      prev.filter((m) => !(m.role === "user" && m.content === pending)),
    );
  }, [storedMessages, streamSettling]);

  useEffect(() => {
    if (streaming || streamSettling) return;
    if (turnSessionRef.current && turnSessionRef.current !== activeSessionId) {
      setLiveMessages([]);
    }
  }, [activeSessionId, streaming, streamSettling]);

  const send = useCallback(
    async (text: string, fetchUrls: string[]) => {
      const trimmed = text.trim();
      if (!trimmed || streaming || streamSettling) return;

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
        await start({
          method: "POST",
          body: {
            message: trimmed,
            session_id: sessionId ?? undefined,
            ...(fetchUrls.length ? { fetch_urls: fetchUrls } : {}),
          },
        });
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
        setStreamSettling(false);
        reset();
      }
    },
    [
      activeSessionId,
      streaming,
      streamSettling,
      setActiveSessionId,
      loadSessions,
      clearMessages,
      reset,
      start,
    ],
  );

  const resetStreamUi = useCallback(() => {
    if (!streaming && !streamSettling) {
      setLiveMessages([]);
      turnSessionRef.current = null;
      streamSessionRef.current = null;
    }
  }, [streaming, streamSettling]);

  const value = useMemo(
    () => ({
      streamState,
      liveMessages,
      streaming,
      streamSettling,
      send,
      abort,
      resetStreamUi,
    }),
    [
      streamState,
      liveMessages,
      streaming,
      streamSettling,
      send,
      abort,
      resetStreamUi,
    ],
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
