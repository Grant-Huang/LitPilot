"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  value: number;
  className?: string;
};

/**
 * 进度数字滚动：从上一个值用 rAF 插值到当前值（~300ms），tabular-nums 防抖动。
 * 尊重 prefers-reduced-motion —— 直接跳到终值。
 */
export function CountUp({ value, className }: Props) {
  const [display, setDisplay] = useState(value);
  const prevRef = useRef(value);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const from = prevRef.current;
    const to = value;
    prevRef.current = value;
    if (from === to) {
      setDisplay(to);
      return;
    }

    const reduce =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setDisplay(to);
      return;
    }

    const duration = 300;
    const start =
      typeof performance !== "undefined" ? performance.now() : Date.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(from + (to - from) * eased));
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [value]);

  return (
    <span className={className} style={{ fontVariantNumeric: "tabular-nums" }}>
      {display}
    </span>
  );
}
