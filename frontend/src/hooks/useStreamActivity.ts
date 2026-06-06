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

  useEffect(() => {
    if (!streaming) return;
    const id = window.setInterval(() => {
      setSnapshot(
        buildStreamActivitySnapshot(
          stream,
          Date.now(),
          lastEventAtRef.current,
          startedAtRef.current,
        ),
      );
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [stream, streaming]);

  return snapshot;
}
