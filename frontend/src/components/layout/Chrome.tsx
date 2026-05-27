"use client";

import { ChatLayoutBridgeProvider } from "@/contexts/ChatLayoutBridgeContext";
import { ChatSessionProvider } from "@/contexts/ChatSessionContext";
import { LiteratureStreamProvider } from "@/contexts/LiteratureStreamContext";
import { LitPilotAppShell } from "./LitPilotAppShell";

export function Chrome({ children }: { children: React.ReactNode }) {
  return (
    <ChatSessionProvider>
      <LiteratureStreamProvider>
        <ChatLayoutBridgeProvider>
          <LitPilotAppShell>{children}</LitPilotAppShell>
        </ChatLayoutBridgeProvider>
      </LiteratureStreamProvider>
    </ChatSessionProvider>
  );
}
