"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { message } from "antd";
import { createInitialStreamState } from "@meso.ai/ui/runtime";
import { LitPilotBrandLockup } from "@/components/brand/LitPilotBrandLockup";
import { LitPilotComposer } from "@/components/chat/LitPilotComposer";
import { LitPilotMessageList } from "@/components/chat/LitPilotMessageList";
import { LitPilotScrollToBottom } from "@/components/chat/LitPilotScrollToBottom";
import { useStreamActivity } from "@/hooks/useStreamActivity";
import { formatStreamActivityHint } from "@/lib/streamActivity";
import { useChatLayoutBridge } from "@/contexts/ChatLayoutBridgeContext";
import { useChatSession } from "@/contexts/ChatSessionContext";
import { useLiteratureStream } from "@/contexts/LiteratureStreamContext";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { chatMessagesToLitPilot } from "@/lib/chatMessageMap";
import {
  streamHasArtifactPane,
  streamStateWithMatrix,
  streamStateWithReview,
} from "@/lib/buildArtifactStream";
import { cloneStreamState } from "@/lib/streamState";
import { loadLibraryItems } from "@/lib/loadLibraryItems";
import { LitPilotArtifactSlot } from "./LitPilotArtifactSlot";
import { stripWorkflowArtifacts } from "./stripWorkflowArtifacts";
import { sessionsApi, type ChatMessage } from "@/lib/api";
import type { LibraryItem } from "@/lib/libraryTypes";
import { settingsApiV2 } from "@/lib/settingsApiV2";

export function LitPilotChatPage() {
  const { setChatLayout } = useChatLayoutBridge();
  const { activeSessionId, messages: storedMessages } = useChatSession();
  const {
    streamState,
    liveMessages,
    streaming,
    streamPending,
    streamSettling,
    liveIntent,
    liveProcessText,
    liveChatText,
    send: sendStream,
    abort,
  } = useLiteratureStream();

  const streamActivity = useStreamActivity(
    streamState,
    streaming || streamPending,
  );
  const streamActivityHint = streamActivity
    ? formatStreamActivityHint(streamActivity)
    : null;

  const [input, setInput] = useState("");
  const [fetchUrls, setFetchUrls] = useState<string[]>([]);
  const [literatureSourceMode, setLiteratureSourceMode] = useState<
    "merge" | "user_only"
  >("merge");
  const [maxFetchUrls, setMaxFetchUrls] = useState(50);
  const [pinnedArtifact, setPinnedArtifact] = useState(
    () => null as ReturnType<typeof cloneStreamState> | null,
  );
  const pinnedSessionRef = useRef<string | null>(null);
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [selectedLibraryId, setSelectedLibraryId] = useState<string | null>(
    null,
  );
  const chatScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void settingsApiV2
      .getSystemCapabilities()
      .then((res) => {
        const caps = res.items || [];
        const source = caps.find((c) => c.capability_id === "literature_source");
        const mode = String(source?.params?.literature_source_mode || "");
        if (mode === "merge" || mode === "user_only") {
          setLiteratureSourceMode(mode);
        }
        const fetch = caps.find((c) => c.capability_id === "web_fetch");
        const maxUrlsRaw = fetch?.params?.max_fetch_urls;
        const maxUrls = Number(maxUrlsRaw);
        if (Number.isFinite(maxUrls)) {
          setMaxFetchUrls(Math.max(1, Math.min(maxUrls, 50)));
        }
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  const loadLibrary = useCallback(async () => {
    setLibraryItems(await loadLibraryItems());
  }, []);

  const streamDone = streamState.status === "done";
  const streamError = streamState.status === "error";
  const activeStreaming =
    streaming || streamDone || streamError || streamSettling;

  const pendingStreamState = useMemo(() => {
    const base = createInitialStreamState();
    return { ...base, status: "streaming" as const };
  }, []);

  const liveStreaming =
    streaming && !streamSettling
      ? stripWorkflowArtifacts(streamState)
      : streamPending
        ? pendingStreamState
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

  const loadSessionArtifacts = useCallback(async (sessionId: string) => {
    try {
      const [review, matrix] = await Promise.all([
        sessionsApi.review(sessionId).catch(() => null),
        sessionsApi.matrix(sessionId).catch(() => null),
      ]);
      if (!review?.content && !matrix?.content) return;
      setPinnedArtifact((prev) => {
        const merged = prev
          ? cloneStreamState(prev)
          : review?.content
            ? streamStateWithReview(review.content, review.filename)
            : streamStateWithMatrix(matrix?.content ?? "");
        const artifacts = { ...merged.artifacts };
        let order = [...merged.artifactOrder];
        const savedArtifacts = [
          review?.content
            ? {
                id: "review-saved",
                lang: "markdown",
                content: review.content,
                updatedAt: review.updated_at ?? "",
              }
            : null,
          matrix?.content
            ? {
                id: "matrix-saved",
                lang: "literature-matrix+markdown",
                content: matrix.content,
                updatedAt: matrix.updated_at ?? "",
              }
            : null,
        ]
          .filter(
            (
              x,
            ): x is {
              id: string;
              lang: string;
              content: string;
              updatedAt: string;
            } => Boolean(x),
          )
          .sort((a, b) => a.updatedAt.localeCompare(b.updatedAt));

        for (const art of savedArtifacts) {
          const id = art.id;
          order = order.includes(id) ? order : [...order, id];
          artifacts[id] = {
            id,
            lang: art.lang,
            content: art.content,
            done: true,
          };
        }
        return {
          ...merged,
          status: "done",
          artifactOrder: order,
          artifacts,
        };
      });
    } catch {
      /* 无已保存 artifact 时忽略 */
    }
  }, []);

  useEffect(() => {
    if (pinnedSessionRef.current === activeSessionId) return;
    pinnedSessionRef.current = activeSessionId;
    setPinnedArtifact(null);
    if (activeSessionId) void loadSessionArtifacts(activeSessionId);
  }, [activeSessionId, loadSessionArtifacts]);

  useEffect(() => {
    void loadLibrary();
  }, [loadLibrary]);

  useEffect(() => {
    if (streamDone || streamError) {
      void loadLibrary();
      if (activeSessionId) void loadSessionArtifacts(activeSessionId);
    }
  }, [streamDone, streamError, loadLibrary, activeSessionId, loadSessionArtifacts]);

  const historyMessages: LitPilotMessage[] = useMemo(() => {
    return [...chatMessagesToLitPilot(storedMessages), ...liveMessages];
  }, [storedMessages, liveMessages]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    const urlsToSend = fetchUrls;
    setFetchUrls([]);
    await sendStream(text, urlsToSend);
  }, [input, fetchUrls, streaming, sendStream]);

  return (
    <div className="litpilot-chat-pane">
      <div className="litpilot-chat-pane__center">
        <div className="litpilot-chat-scroll" ref={chatScrollRef}>
          <LitPilotMessageList
            messages={historyMessages}
            streaming={liveStreaming}
            liveIntent={liveIntent}
            liveProcessText={liveProcessText}
            liveChatText={liveChatText}
            hasArtifact={hasArtifactPane}
            scrollContainerRef={chatScrollRef}
            scrollResetKey={activeSessionId}
            emptyStateAlign="top"
            emptyState={
              historyMessages.length === 0 && !streaming && !streamSettling ? (
                <div className="litpilot-chat-welcome">
                  <LitPilotBrandLockup
                    markSize={40}
                    wordmarkSize={22}
                    pageTitle="文献综述"
                    className="litpilot-chat-welcome__brand"
                  />
                  <p style={{ color: "var(--color-text-muted)" }}>
                    描述研究主题，左侧显示执行过程，综述与矩阵在右侧 Artifact 面板查看。
                  </p>
                </div>
              ) : null
            }
          />
          <LitPilotScrollToBottom scrollContainerRef={chatScrollRef} />
        </div>
        <LitPilotComposer
          input={input}
          onInputChange={setInput}
          fetchUrls={fetchUrls}
          onFetchUrlsChange={setFetchUrls}
          maxFetchUrls={maxFetchUrls}
          literatureSourceMode={literatureSourceMode}
          streaming={streaming || streamPending}
          streamPending={streamPending}
          streamActivityHint={streamActivityHint}
          streamActivityLevel={streamActivity?.level ?? null}
          onSend={() => void send()}
          onAbort={abort}
        />
      </div>
    </div>
  );
}
