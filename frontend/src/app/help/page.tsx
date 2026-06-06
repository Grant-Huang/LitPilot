"use client";

import { Suspense, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Spin } from "antd";
import { HelpCenterView } from "@/components/help/HelpCenterView";
import {
  DEFAULT_HELP_PAGE_ID,
  HELP_PAGE_MAP,
  type HelpPageId,
} from "@/content/help";

function parseHelpPageId(raw: string | null): HelpPageId {
  if (raw && raw in HELP_PAGE_MAP) return raw as HelpPageId;
  return DEFAULT_HELP_PAGE_ID;
}

function HelpPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const pageId = parseHelpPageId(searchParams.get("page"));

  const onPageChange = useCallback(
    (id: HelpPageId) => {
      const next = id === DEFAULT_HELP_PAGE_ID ? "/help" : `/help?page=${encodeURIComponent(id)}`;
      router.replace(next, { scroll: false });
    },
    [router],
  );

  return <HelpCenterView pageId={pageId} onPageChange={onPageChange} />;
}

export default function HelpPage() {
  return (
    <Suspense
      fallback={
        <div className="functional-doc-shell functional-doc-shell--loading">
          <Spin />
        </div>
      }
    >
      <HelpPageInner />
    </Suspense>
  );
}
