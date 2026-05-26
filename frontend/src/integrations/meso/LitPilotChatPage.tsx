"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { message } from "antd";
import { LitPilotComposer } from "@/components/chat/LitPilotComposer";
import { useSSEStream } from "@meso/ui";
import { LitPilotMessageList } from "@/components/chat/LitPilotMessageList";
import { useChatLayoutBridge } from "@/contexts/ChatLayoutBridgeContext";
import { useChatSession } from "@/contexts/ChatSessionContext";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { collectFailuresFromStream } from "@/lib/collectFailures";
import {
  collectExecutionTraceFromStream,
  mergeThinkIntoTrace,
} from "@/lib/executionTrace";
import {
  streamHasArtifactPane,
  streamStateWithReview,
} from "@/lib/buildArtifactStream";
import { cloneStreamState } from "@/lib/streamState";
import { LitPilotArtifactSlot } from "./LitPilotArtifactSlot";
import { stripWorkflowArtifacts } from "./stripWorkflowArtifacts";
import {
  libraryApi,
  sessionsApi,
  settingsApi,
  type ChatMessage,
} from "@/lib/api";
import { normalizeLibraryItem, type LibraryItem } from "@/lib/libraryTypes";

function mapStoredMessages(msgs: ChatMessage[]): LitPilotMessage[] {
  return msgs.map((m, i) => {
    const meta = m.meta;
    const failed = meta?.failed_literature;
    const think = meta?.think || meta?.thinkContent;
    const trace = mergeThinkIntoTrace(meta?.execution_trace, think);
    const hasExtras =
      m.role === "assistant" &&
      (think || failed?.length || trace);
    return {
      id: `hist-${i}`,
      role: m.role as "user" | "assistant",
      content: m.content,
      extras: hasExtras
        ? {
            thinkContent: think,
            failedLiterature: failed,
            executionTrace: trace,
          }
        : undefined,
    };
  });
}

export function LitPilotChatPage() {
  const { setChatLayout } = useChatLayoutBridge();
  const {
    activeSessionId,
    messages: storedMessages,
    loadSessions,
    handleNewSession,
    setActiveSessionId,
    handleSelectSession,
  } = useChatSession();

  const { state: streamState, start, abort, reset } = useSSEStream(
    "/api/chat/literature/execute",
  );

  const [input, setInput] = useState("");
  const [fetchUrls, setFetchUrls] = useState<string[]>([]);
  const [literatureSourceMode, setLiteratureSourceMode] = useState<
    "merge" | "user_only"
  >("merge");
  const [liveMessages, setLiveMessages] = useState<LitPilotMessage[]>([]);
  const [pinnedArtifact, setPinnedArtifact] = useState(
    () => null as ReturnType<typeof cloneStreamState> | null,
  );
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [selectedLibraryId, setSelectedLibraryId] = useState<string | null>(
    null,
  );
  const streamStartedRef = useRef(false);

  useEffect(() => {
    void settingsApi.getAgent().then((cfg) => {
      if (
        cfg.literature_source_mode === "merge" ||
        cfg.literature_source_mode === "user_only"
      ) {
        setLiteratureSourceMode(cfg.literature_source_mode);
      }
    });
  }, []);

  const loadLibrary = useCallback(async () => {
    try {
      const data = await libraryApi.items();
      setLibraryItems(data.items || []);
    } catch {
      try {
        const legacy = await libraryApi.refs();
        const raw =
          (legacy.items as Record<string, unknown>[]) ||
          (legacy.index?.refs as Record<string, unknown>[]) ||
          [];
        setLibraryItems(raw.map((r) => normalizeLibraryItem(r)));
      } catch {
        /* ignore */
      }
    }
  }, []);

  const streaming = streamState.status === "streaming";
  const streamDone = streamState.status === "done";
  const streamError = streamState.status === "error";
  const activeStreaming = streaming || streamDone || streamError;

  const liveStreaming = activeStreaming
    ? stripWorkflowArtifacts(streamState)
    : undefined;

  useEffect(() => {
    if (!activeStreaming) return;
    if (streamHasArtifactPane(streamState)) {
      setPinnedArtifact(cloneStreamState(streamState));
    }
  }, [streamState, activeStreaming]);

  const artifactStream = activeStreaming
    ? streamState
    : pinnedArtifact ?? streamState;

  const hasArtifactPane = streamHasArtifactPane(artifactStream);

  const artifactSlot = useMemo(
    () =>
      hasArtifactPane ? (
        <LitPilotArtifactSlot
          streamState={artifactStream}
          reviewFilename="review-latest.md"
          libraryItems={libraryItems}
          selectedLibraryId={selectedLibraryId}
          onSelectLibraryId={setSelectedLibraryId}
          activeSessionId={activeSessionId}
          onLiteratureDetailOpen={(open) =>
            setChatLayout({ literatureDetailOpen: open })
          }
        />
      ) : null,
    [
      hasArtifactPane,
      artifactStream,
      libraryItems,
      selectedLibraryId,
      activeSessionId,
      setChatLayout,
    ],
  );

  useEffect(() => {
    setChatLayout({
      hasArtifact: hasArtifactPane,
      artifactPanel: artifactSlot,
    });
  }, [hasArtifactPane, artifactSlot, setChatLayout]);

  useEffect(() => {
    if (!hasArtifactPane) {
      setChatLayout({ literatureDetailOpen: false });
      setSelectedLibraryId(null);
    }
  }, [hasArtifactPane, setChatLayout]);

  const loadSessionReview = useCallback(async (sessionId: string) => {
    try {
      const review = await sessionsApi.review(sessionId);
      if (!review?.content) return;
      setPinnedArtifact((prev) => {
        const merged = prev
          ? cloneStreamState(prev)
          : streamStateWithReview(review.content, review.filename);
        const id = "review-saved";
        const order = merged.artifactOrder.includes(id)
          ? merged.artifactOrder
          : [...merged.artifactOrder, id];
        return {
          ...merged,
          artifactOrder: order,
          artifacts: {
            ...merged.artifacts,
            [id]: {
              id,
              lang: "markdown",
              content: review.content,
              done: true,
            },
          },
        };
      });
    } catch {
      /* 无综述文件时忽略 */
    }
  }, []);

  useEffect(() => {
    if (activeSessionId) void loadSessionReview(activeSessionId);
  }, [activeSessionId, loadSessionReview]);

  useEffect(() => {
    void loadLibrary();
  }, [loadLibrary]);

  useEffect(() => {
    for (const ext of streamState.extensionLog) {
      const name = ext.payload.name;
      const data = ext.payload.data as
        | {
            session_id?: string;
            title?: string;
            added?: number;
            merged?: number;
          }
        | undefined;
      if (name === "library_updated") {
        void loadLibrary();
        if (data?.added != null) {
          message.success(
            `文献库已更新：新增 ${data.added}，合并 ${data.merged ?? 0}`,
          );
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
      if (name === "session_title" && data?.session_id && data?.title) {
        void loadSessions();
      }
    }
  }, [streamState.extensionLog, setActiveSessionId, loadSessions, loadLibrary]);

  const historyMessages: LitPilotMessage[] = useMemo(() => {
    return [...mapStoredMessages(storedMessages), ...liveMessages];
  }, [storedMessages, liveMessages]);

  const commitStreamTurn = useCallback(() => {
    if (!streamStartedRef.current) return;
    const assistantText =
      streamState.textContent ||
      (streamState.errorMessage ? `错误: ${streamState.errorMessage}` : "");
    const failures = collectFailuresFromStream(streamState);
    const think = streamState.thinkContent?.trim();
    const executionTrace = collectExecutionTraceFromStream(streamState);

    if (
      assistantText ||
      think ||
      failures.length ||
      executionTrace.stages.length ||
      executionTrace.tools.length ||
      executionTrace.workflows.length
    ) {
      setLiveMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: assistantText,
          extras: {
            thinkContent: think || undefined,
            failedLiterature: failures.length ? failures : undefined,
            executionTrace,
          },
        },
      ]);
    }
  }, [streamState]);

  useEffect(() => {
    if (streamStartedRef.current && (streamDone || streamError)) {
      commitStreamTurn();
      reset();
      streamStartedRef.current = false;
      void loadSessions();
      void loadLibrary();
      if (activeSessionId) {
        void handleSelectSession(activeSessionId);
        void loadSessionReview(activeSessionId);
      }
    }
  }, [
    streamDone,
    streamError,
    commitStreamTurn,
    reset,
    loadSessions,
    loadLibrary,
    activeSessionId,
    handleSelectSession,
    loadSessionReview,
  ]);

  useEffect(() => {
    setLiveMessages([]);
  }, [activeSessionId]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;

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

    setLiveMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: "user", content: text },
    ]);
    setInput("");
    const urlsToSend = fetchUrls;
    setFetchUrls([]);
    reset();
    streamStartedRef.current = true;

    try {
      await start({
        method: "POST",
        body: {
          message: text,
          session_id: sessionId ?? undefined,
          ...(urlsToSend.length ? { fetch_urls: urlsToSend } : {}),
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
      reset();
    }
  }, [
    input,
    fetchUrls,
    streaming,
    activeSessionId,
    setActiveSessionId,
    loadSessions,
    reset,
    start,
  ]);

  return (
    <div className="litpilot-chat-pane">
      <div className="litpilot-chat-pane__center">
        <div className="litpilot-chat-scroll">
          <LitPilotMessageList
            messages={historyMessages}
            streaming={liveStreaming}
            emptyStateAlign="top"
            emptyState={
              historyMessages.length === 0 && !activeStreaming ? (
                <div className="litpilot-chat-welcome">
                  <h2>LitPilot 文献综述</h2>
                  <p style={{ color: "var(--color-text-muted)" }}>
                    描述研究主题，系统将检索文献并生成 APA / ACM 格式综述。执行过程中会在此显示阶段、思考与工具调用进度。
                  </p>
                </div>
              ) : null
            }
          />
        </div>
        <LitPilotComposer
          input={input}
          onInputChange={setInput}
          fetchUrls={fetchUrls}
          onFetchUrlsChange={setFetchUrls}
          literatureSourceMode={literatureSourceMode}
          streaming={streaming}
          onSend={() => void send()}
          onAbort={abort}
        />
      </div>
    </div>
  );
}
