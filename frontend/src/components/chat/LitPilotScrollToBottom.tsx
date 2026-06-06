"use client";

import { useCallback, useEffect, useState, type RefObject } from "react";
import { DownOutlined } from "@ant-design/icons";

const BOTTOM_THRESHOLD_PX = 80;

type Props = {
  scrollContainerRef: RefObject<HTMLElement | null>;
};

export function LitPilotScrollToBottom({ scrollContainerRef }: Props) {
  const [visible, setVisible] = useState(false);

  const update = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) {
      setVisible(false);
      return;
    }
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD_PX;
    setVisible(!nearBottom && el.scrollHeight > el.clientHeight + 40);
  }, [scrollContainerRef]);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      ro.disconnect();
    };
  }, [scrollContainerRef, update]);

  if (!visible) return null;

  return (
    <button
      type="button"
      className="litpilot-scroll-bottom"
      aria-label="回到底部"
      onClick={() => {
        const el = scrollContainerRef.current;
        if (!el) return;
        el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      }}
    >
      <DownOutlined />
    </button>
  );
}
