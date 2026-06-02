"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  DEFAULT_HELP_PAGE_ID,
  HelpCenterModal,
  type HelpPageId,
} from "@/components/help/HelpCenterModal";

type HelpCenterContextValue = {
  openHelp: (pageId?: HelpPageId) => void;
  closeHelp: () => void;
};

const HelpCenterContext = createContext<HelpCenterContextValue | null>(null);

export function HelpCenterProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [pageId, setPageId] = useState<HelpPageId>(DEFAULT_HELP_PAGE_ID);

  const openHelp = useCallback((id?: HelpPageId) => {
    if (id) setPageId(id);
    setOpen(true);
  }, []);

  const closeHelp = useCallback(() => setOpen(false), []);

  const value = useMemo(
    () => ({ openHelp, closeHelp }),
    [openHelp, closeHelp],
  );

  return (
    <HelpCenterContext.Provider value={value}>
      {children}
      <HelpCenterModal
        open={open}
        pageId={pageId}
        onClose={closeHelp}
        onPageChange={setPageId}
      />
    </HelpCenterContext.Provider>
  );
}

export function useHelpCenter() {
  const ctx = useContext(HelpCenterContext);
  if (!ctx) {
    throw new Error("HelpCenterProvider required");
  }
  return ctx;
}
