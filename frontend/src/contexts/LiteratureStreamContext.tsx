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
import { formatLiteratureIntentLabel } from "@/lib/literatureIntent";
import { sessionsApi } from "@/lib/api";

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
  const extensionHandledRef = useRef(0);

  const streaming = streamState.status === "streaming";
  const streamDone = streamState.status === "done";
  const streamError = streamState.status === "error";

  useEffect(() => {
    if (!streamStartedRef.current || !(streamDone || streamError)) return;
    const sid = turnSessionRef.current || activeSessionId;
    reset();
    streamStartedRef.current = false;
    turnSessionRef.current = null;
    void loadSessions();
    if (sid) {
      void handleSelectSession(sid);
    }
  }, [
    streamDone,
    streamError,
    reset,
    loadSessions,
    activeSessionId,
    handleSelectSession,
  ]);

  useEffect(() => {
    const log = streamState.extensionLog;
    for (let i = extensionHandledRef.current; i < log.length; i += 1) {
      const ext = log[i];
      const name = ext.payload.name;
      const data = ext.payload.data as
        | {
            session_id?: string;
            title?: string;
            added?: number;
            merged?: number;
            intent?: string;
          }
        | undefined;
      if (name === "literature_intent" && data?.intent && isChat) {
        message.info(formatLiteratureIntentLabel(data.intent));
      }
      if (name === "literature_search_plan" && isChat) {
        const queries = (data as { queries?: string[] } | undefined)?.queries;
        if (queries?.length) {
          message.info(`检索扩展：${queries.length} 组 query`);
        }
      }
      if (name === "literature_paper_index" && isChat) {
        const count = (data as { count?: number; extracted?: number } | undefined)?.count;
        const extracted = (data as { extracted?: number } | undefined)?.extracted;
        if (typeof count === "number") {
          message.info(`文献结构化：${count} 篇${typeof extracted === "number" ? `（本轮 +${extracted}）` : ""}`);
        }
      }
      if (name === "literature_subtopic_plan" && isChat) {
        const count = (data as { count?: number } | undefined)?.count;
        if (typeof count === "number" && count >= 2) {
          message.info(`已拆分为 ${count} 个子主题，将分别检索`);
        }
      }
      if (name === "literature_outline" && isChat) {
        const sectionCount = (data as { section_count?: number } | undefined)?.section_count;
        if (typeof sectionCount === "number") {
          message.info(`大纲已生成：${sectionCount} 个章节（见右侧「大纲」）`);
        }
      }
      if (name === "literature_refine_report" && isChat) {
        const missing = (data as { missing_sections?: string[] } | undefined)?.missing_sections;
        if (missing?.length) {
          message.warning(`后处理：${missing.length} 个章节标题未在正文中出现`);
        }
      }
      if (name === "literature_section_refine" && isChat) {
        const mode = (data as { mode?: string } | undefined)?.mode;
        const titles = (data as { target_titles?: string[] } | undefined)?.target_titles;
        if (mode === "partial" && titles?.length) {
          message.info(`章节级修订：${titles.join("、")}`);
        }
      }
      if (name === "session" && data?.session_id) {
        const sid = String(data.session_id);
        setActiveSessionId(sid);
        if (typeof window !== "undefined") {
          localStorage.setItem("litpilot:active-session", sid);
        }
        void loadSessions();
      }
      if (name === "session_title") {
        void loadSessions();
      }
    }
    extensionHandledRef.current = log.length;
  }, [streamState.extensionLog, isChat, setActiveSessionId, loadSessions]);

  useEffect(() => {
    if (!isChat || !activeSessionId) return;
    void handleSelectSession(activeSessionId);
  }, [isChat, activeSessionId, handleSelectSession]);

  useEffect(() => {
    if (streaming || !activeSessionId) return;
    const last = storedMessages[storedMessages.length - 1];
    if (!last || last.role !== "user") return;
    const timer = window.setInterval(() => {
      void handleSelectSession(activeSessionId);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [streaming, activeSessionId, storedMessages, handleSelectSession]);

  useEffect(() => {
    if (streaming) return;
    if (turnSessionRef.current && turnSessionRef.current !== activeSessionId) {
      setLiveMessages([]);
    }
  }, [activeSessionId, streaming]);

  useEffect(() => {
    if (streamDone) setLiveMessages([]);
  }, [streamDone]);

  const send = useCallback(
    async (text: string, fetchUrls: string[]) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;

      let sessionId = activeSessionId;
      if (!sessionId) {
        const meta = await sessionsApi.create();
        sessionId = meta.id;
        setActiveSessionId(sessionId);
        if (typeof window !== "undefined") {
          localStorage.setItem("litpilot:active-session", sessionId);
        }
        await loadSessions();
      }

      turnSessionRef.current = sessionId;
      reset();
      streamStartedRef.current = true;
      void handleSelectSession(sessionId);

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
