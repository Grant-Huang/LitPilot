"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { message } from "antd";
import { LitPilotBrandLockup } from "@/components/brand/LitPilotBrandLockup";
import { LitPilotComposer } from "@/components/chat/LitPilotComposer";
import { LitPilotMessageList } from "@/components/chat/LitPilotMessageList";
import { useChatLayoutBridge } from "@/contexts/ChatLayoutBridgeContext";
import { useChatSession } from "@/contexts/ChatSessionContext";
import { useLiteratureStream } from "@/contexts/LiteratureStreamContext";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { mergeThinkIntoTrace } from "@/lib/executionTrace";
import {
  streamHasArtifactPane,
  streamStateWithReview,
} from "@/lib/buildArtifactStream";
import { cloneStreamState } from "@/lib/streamState";
import { LitPilotArtifactSlot } from "./LitPilotArtifactSlot";
import { stripWorkflowArtifacts } from "./stripWorkflowArtifacts";
import { libraryApi, sessionsApi, settingsApi, type ChatMessage } from "@/lib/api";
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
  const { activeSessionId } = useChatSession();
  const {
    streamState,
    liveMessages,
    streaming,
    send: sendStream,
    abort,
  } = useLiteratureStream();

  const [input, setInput] = useState("");
  const [fetchUrls, setFetchUrls] = useState<string[]>([]);
  const [literatureSourceMode, setLiteratureSourceMode] = useState<
    "merge" | "user_only"
  >("merge");
  const [maxFetchUrls, setMaxFetchUrls] = useState(50);
  const [pinnedArtifact, setPinnedArtifact] = useState(
    () => null as ReturnType<typeof cloneStreamState> | null,
  );
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [selectedLibraryId, setSelectedLibraryId] = useState<string | null>(
    null,
  );
  const { messages: storedMessages } = useChatSession();

  useEffect(() => {
    void settingsApi.getAgent().then((cfg) => {
      if (
        cfg.literature_source_mode === "merge" ||
        cfg.literature_source_mode === "user_only"
      ) {
        setLiteratureSourceMode(cfg.literature_source_mode);
      }
      if (cfg.max_fetch_urls != null) {
        setMaxFetchUrls(Math.max(1, Math.min(cfg.max_fetch_urls, 50)));
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
    if (streamDone || streamError) {
      void loadLibrary();
      if (activeSessionId) void loadSessionReview(activeSessionId);
    }
  }, [streamDone, streamError, loadLibrary, activeSessionId, loadSessionReview]);

  const historyMessages: LitPilotMessage[] = useMemo(() => {
    return [...mapStoredMessages(storedMessages), ...liveMessages];
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
        <div className="litpilot-chat-scroll">
          <LitPilotMessageList
            messages={historyMessages}
            streaming={liveStreaming}
            emptyStateAlign="top"
            emptyState={
              historyMessages.length === 0 && !activeStreaming ? (
                <div className="litpilot-chat-welcome">
                  <LitPilotBrandLockup
                    markSize={40}
                    wordmarkSize={22}
                    pageTitle="文献综述"
                    className="litpilot-chat-welcome__brand"
                  />
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
          maxFetchUrls={maxFetchUrls}
          literatureSourceMode={literatureSourceMode}
          streaming={streaming}
          onSend={() => void send()}
          onAbort={abort}
        />
      </div>
    </div>
  );
}
