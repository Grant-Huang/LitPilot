"use client";

import { useEffect, useRef, useState } from "react";
import type { StreamState } from "@meso.ai/ui";
import {
  buildStreamActivitySnapshot,
  streamActivityFingerprint,
  type StreamActivitySnapshot,
} from "@/lib/streamActivity";

const TICK_MS = 1000;

export function useStreamActivity(
  stream: StreamState,
  streaming: boolean,
): StreamActivitySnapshot | null {
  const [snapshot, setSnapshot] = useState<StreamActivitySnapshot | null>(null);
  const lastEventAtRef = useRef<number>(Date.now());
  const startedAtRef = useRef<number>(Date.now());
  const fingerprintRef = useRef("");

  useEffect(() => {
    if (!streaming) {
      setSnapshot(null);
      fingerprintRef.current = "";
      return;
    }
    if (!fingerprintRef.current) {
      startedAtRef.current = Date.now();
      lastEventAtRef.current = Date.now();
    }
    const fp = streamActivityFingerprint(stream);
    if (fp !== fingerprintRef.current) {
      fingerprintRef.current = fp;
      lastEventAtRef.current = Date.now();
    }
    setSnapshot(
      buildStreamActivitySnapshot(
        stream,
        Date.now(),
        lastEventAtRef.current,
        startedAtRef.current,
      ),
    );
  }, [stream, streaming]);

  // 关键修复：之前 deps 包含 stream，每来一帧 SSE 都重新创建 1s 定时器；
  // 改用 ref 持有最新 stream，定时器只随 streaming 启停。
  const streamRef = useRef(stream);
  useEffect(() => {
    streamRef.current = stream;
  }, [stream]);

  useEffect(() => {
    if (!streaming) return;
    const id = window.setInterval(() => {
      setSnapshot(
        buildStreamActivitySnapshot(
          streamRef.current,
          Date.now(),
          lastEventAtRef.current,
          startedAtRef.current,
        ),
      );
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [streaming]);

  return snapshot;
}
