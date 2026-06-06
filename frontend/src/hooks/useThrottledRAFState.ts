"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Buffers high-frequency updates and flushes at most once per animation frame.
 */
export function useThrottledRAFState<T>(initial: T) {
  const [state, setState] = useState<T>(initial);
  const pendingRef = useRef<T>(initial);
  const rafRef = useRef<number | null>(null);

  const flush = useCallback(() => {
    rafRef.current = null;
    setState(pendingRef.current);
  }, []);

  const scheduleFlush = useCallback(() => {
    if (rafRef.current !== null) return;
    rafRef.current = requestAnimationFrame(flush);
  }, [flush]);

  const update = useCallback(
    (updater: T | ((prev: T) => T)) => {
      pendingRef.current =
        typeof updater === "function"
          ? (updater as (prev: T) => T)(pendingRef.current)
          : updater;
      scheduleFlush();
    },
    [scheduleFlush],
  );

  const commitNow = useCallback(
    (updater: T | ((prev: T) => T)) => {
      pendingRef.current =
        typeof updater === "function"
          ? (updater as (prev: T) => T)(pendingRef.current)
          : updater;
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      setState(pendingRef.current);
    },
    [],
  );

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, []);

  return { state, update, commitNow, pendingRef } as const;
}
