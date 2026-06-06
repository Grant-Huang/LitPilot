"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  applyEvent,
  createInitialStreamState,
  parseSSELine,
  type SSEEvent,
  type StreamState,
} from "@meso.ai/ui/runtime";
import type { StreamCallbacks, StreamOptions } from "@meso.ai/ui";
import { useThrottledRAFState } from "@/hooks/useThrottledRAFState";

export type BatchedStreamStartOptions = StreamOptions & {
  /** Override hook URL (e.g. task stream with since=). */
  url?: string;
  /** Keep current stream UI state when reconnecting. */
  preserveState?: boolean;
  /** Called after each parsed SSE event (for resume cursor). */
  onEventApplied?: (event: SSEEvent, index: number) => void;
};

function dispatchCallbacks(
  event: SSEEvent,
  state: StreamState,
  callbacks: StreamCallbacks | undefined,
): void {
  if (!callbacks) return;
  switch (event.type) {
    case "capabilities":
      callbacks.onCapabilities?.(event.payload);
      break;
    case "stage":
      callbacks.onStageChange?.(event.payload);
      break;
    case "memory":
      callbacks.onMemoryRecalled?.(event.payload.snippets);
      break;
    case "memory_saved":
      callbacks.onMemorySaved?.(event.payload);
      break;
    case "soul":
      callbacks.onSoulActivated?.(event.payload);
      break;
    case "skill_active":
      callbacks.onSkillActivated?.(event.payload);
      break;
    case "tool_call":
      callbacks.onToolCall?.(event.payload);
      break;
    case "tool_result":
      callbacks.onToolResult?.(event.payload);
      break;
    case "resource_read":
      callbacks.onResourceRead?.(event.payload);
      break;
    case "resource_content":
      callbacks.onResourceContent?.(event.payload);
      break;
    case "artifact": {
      const artifact = state.artifacts[event.payload.id];
      if (artifact) callbacks.onArtifact?.(artifact);
      break;
    }
    case "error":
      callbacks.onError?.(event.payload.message, event.payload.code);
      break;
    case "done":
      callbacks.onDone?.(state);
      break;
    default:
      break;
  }
}

/**
 * Meso SSE hook with rAF-batched state updates (≤1 React commit per frame).
 */
export function useBatchedSSEStream(url: string, callbacks?: StreamCallbacks) {
  const { state, update, commitNow, pendingRef } = useThrottledRAFState<StreamState>(
    createInitialStreamState(),
  );
  const controllerRef = useRef<AbortController | null>(null);
  const callbacksRef = useRef(callbacks);
  callbacksRef.current = callbacks;
  const workingRef = useRef<StreamState>(createInitialStreamState());

  const applyStreamEvent = useCallback(
    (event: SSEEvent) => {
      const next = applyEvent(workingRef.current, event);
      workingRef.current = next;
      pendingRef.current = next;
      if (event.type === "done" || event.type === "error") {
        commitNow(next);
      } else {
        update(next);
      }
      dispatchCallbacks(event, next, callbacksRef.current);
      return next;
    },
    [commitNow, pendingRef, update],
  );

  const abort = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    const idle = createInitialStreamState();
    workingRef.current = idle;
    commitNow(idle);
  }, [commitNow]);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    const initial = createInitialStreamState();
    workingRef.current = initial;
    commitNow(initial);
  }, [commitNow]);

  const start = useCallback(
    async (options?: BatchedStreamStartOptions) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      const targetUrl = options?.url ?? url;
      if (!options?.preserveState) {
        const initial = { ...createInitialStreamState(), status: "streaming" as const };
        workingRef.current = initial;
        commitNow(initial);
      } else if (workingRef.current.status !== "streaming") {
        const resumed = { ...workingRef.current, status: "streaming" as const };
        workingRef.current = resumed;
        commitNow(resumed);
      }

      const method = options?.method ?? (options?.body ? "POST" : "GET");
      let eventIndex = 0;
      try {
        const response = await fetch(targetUrl, {
          method,
          headers: {
            ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
            ...options?.headers,
          },
          body: options?.body ? JSON.stringify(options.body) : undefined,
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error("Empty SSE body");

        const decoder = new TextDecoder();
        let buffer = "";

        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            const event = parseSSELine(line);
            if (!event) continue;
            eventIndex += 1;
            applyStreamEvent(event);
            options?.onEventApplied?.(event, eventIndex);
            if (event.type === "done" || event.type === "error") return;
          }
        }
      } catch (e: unknown) {
        if (e instanceof Error && e.name === "AbortError") return;
        const message = e instanceof Error ? e.message : String(e);
        applyStreamEvent({
          type: "error",
          schema_version: "1.0",
          payload: { message },
        });
        callbacksRef.current?.onError?.(message);
      }
    },
    [applyStreamEvent, commitNow, url],
  );

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  return { state, start, abort, reset };
}
