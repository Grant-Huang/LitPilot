"use client";

import { AppNavigationProvider } from "@/contexts/AppNavigationContext";
import { ChatLayoutBridgeProvider } from "@/contexts/ChatLayoutBridgeContext";
import { ChatSessionProvider } from "@/contexts/ChatSessionContext";
import { LiteratureTaskProvider } from "@/contexts/LiteratureTaskContext";
import { LitPilotAppShell } from "./LitPilotAppShell";

export function Chrome({ children }: { children: React.ReactNode }) {
  return (
    <ChatSessionProvider>
      <LiteratureTaskProvider>
        <AppNavigationProvider>
          <ChatLayoutBridgeProvider>
            <LitPilotAppShell>{children}</LitPilotAppShell>
          </ChatLayoutBridgeProvider>
        </AppNavigationProvider>
      </LiteratureTaskProvider>
    </ChatSessionProvider>
  );
}
