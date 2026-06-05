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
import { message } from "antd";
import { useSSEStream } from "@meso.ai/ui";
import { useChatSession } from "@/contexts/ChatSessionContext";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { handleLiteratureExtensionEvent } from "@/lib/literatureExtensionHandlers";
import { persistActiveSession } from "@/lib/sessionStorage";
import { sessionsApi } from "@/lib/api";
import {
  clearClarificationUnreadTitle,
  setClarificationUnreadTitle,
} from "@/lib/clarificationTitle";

type LiteratureStreamContextValue = {
  streamState: ReturnType<typeof useSSEStream>["state"];
  liveMessages: LitPilotMessage[];
  streaming: boolean;
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
  } = useChatSession();

  const { state: streamState, start, abort, reset } = useSSEStream(
    "/api/chat/literature/execute",
  );

  const [liveMessages, setLiveMessages] = useState<LitPilotMessage[]>([]);
  const streamStartedRef = useRef(false);
  const turnSessionRef = useRef<string | null>(null);
  /** 本轮 SSE 中 extension.session 下发的权威 session_id（可能与发送时不一致） */
  const streamSessionRef = useRef<string | null>(null);
  const pendingUserTextRef = useRef<string | null>(null);
  const extensionHandledRef = useRef(0);

  const streaming = streamState.status === "streaming";
  const streamDone = streamState.status === "done";
  const streamError = streamState.status === "error";

  useEffect(() => {
    if (!streamStartedRef.current || !(streamDone || streamError)) return;
    const sid =
      streamSessionRef.current || activeSessionId || turnSessionRef.current;
    streamStartedRef.current = false;
    void (async () => {
      try {
        await loadSessions();
        if (sid) await handleSelectSession(sid);
      } finally {
        reset();
        turnSessionRef.current = null;
        streamSessionRef.current = null;
        setLiveMessages([]);
      }
    })();
  }, [streamDone, streamError, reset, loadSessions, handleSelectSession]);

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
      if (ext.payload.name === "literature_clarification") {
        const kind = (ext.payload.data as Record<string, unknown> | undefined)
          ?.kind;
        setClarificationUnreadTitle(
          typeof kind === "string" ? kind : undefined,
        );
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
    if (!pending) return;
    const persisted = storedMessages.some(
      (m) => m.role === "user" && m.content === pending,
    );
    if (persisted) {
      pendingUserTextRef.current = null;
      setLiveMessages([]);
    }
  }, [storedMessages]);

  useEffect(() => {
    if (streaming || streamStartedRef.current) return;
    if (turnSessionRef.current && turnSessionRef.current !== activeSessionId) {
      setLiveMessages([]);
    }
  }, [activeSessionId, streaming]);

  const send = useCallback(
    async (text: string, fetchUrls: string[]) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;

      let sessionId = activeSessionId;
      if (!sessionId) {
        const meta = await sessionsApi.create();
        sessionId = meta.id;
        setActiveSessionId(sessionId);
        persistActiveSession(sessionId);
        await loadSessions();
      }

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
        message.error(errText);
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
        reset();
      }
    },
    [
      activeSessionId,
      streaming,
      setActiveSessionId,
      loadSessions,
      reset,
      start,
    ],
  );

  const resetStreamUi = useCallback(() => {
    if (!streaming) {
      setLiveMessages([]);
      turnSessionRef.current = null;
    }
  }, [streaming]);

  const value = useMemo(
    () => ({
      streamState,
      liveMessages,
      streaming,
      send,
      abort,
      resetStreamUi,
    }),
    [streamState, liveMessages, streaming, send, abort, resetStreamUi],
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
