"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { sessionsApi, type ChatMessage, type SessionMeta } from "@/lib/api";

type ChatSessionContextValue = {
  sessions: SessionMeta[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  loadSessions: () => Promise<void>;
  handleNewSession: () => Promise<void>;
  handleSelectSession: (id: string) => Promise<void>;
  handleDeleteSession: (id: string) => Promise<void>;
  handleRenameSession: (id: string, title: string) => Promise<void>;
  handleTogglePinSession: (id: string, pinned: boolean) => Promise<void>;
  setActiveSessionId: (id: string | null) => void;
};

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null);

const STORAGE_KEY = "litpilot:active-session";

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const loadSessions = useCallback(async () => {
    const list = await sessionsApi.list();
    setSessions(list);
  }, []);

  const loadMessages = useCallback(async (id: string) => {
    const msgs = await sessionsApi.messages(id);
    setMessages(msgs);
  }, []);

  const handleNewSession = useCallback(async () => {
    const meta = await sessionsApi.create();
    setActiveSessionId(meta.id);
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, meta.id);
    }
    setMessages([]);
    await loadSessions();
  }, [loadSessions]);

  const handleSelectSession = useCallback(
    async (id: string) => {
      setActiveSessionId(id);
      if (typeof window !== "undefined") {
        localStorage.setItem(STORAGE_KEY, id);
      }
      await loadMessages(id);
    },
    [loadMessages],
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      await sessionsApi.delete(id);
      if (activeSessionId === id) {
        setActiveSessionId(null);
        setMessages([]);
        if (typeof window !== "undefined") {
          localStorage.removeItem(STORAGE_KEY);
        }
      }
      await loadSessions();
    },
    [activeSessionId, loadSessions],
  );

  const handleRenameSession = useCallback(
    async (id: string, title: string) => {
      await sessionsApi.update(id, { title });
      await loadSessions();
    },
    [loadSessions],
  );

  const handleTogglePinSession = useCallback(
    async (id: string, pinned: boolean) => {
      await sessionsApi.update(id, { pinned });
      await loadSessions();
    },
    [loadSessions],
  );

  useEffect(() => {
    void loadSessions().then(async () => {
      const stored =
        typeof window !== "undefined"
          ? localStorage.getItem(STORAGE_KEY)
          : null;
      if (stored) {
        try {
          await handleSelectSession(stored);
        } catch {
          /* session may be deleted */
        }
      }
    });
  }, [loadSessions, handleSelectSession]);

  const value = useMemo(
    () => ({
      sessions,
      activeSessionId,
      messages,
      loadSessions,
      handleNewSession,
      handleSelectSession,
      handleDeleteSession,
      handleRenameSession,
      handleTogglePinSession,
      setActiveSessionId,
    }),
    [
      sessions,
      activeSessionId,
      messages,
      loadSessions,
      handleNewSession,
      handleSelectSession,
      handleDeleteSession,
      handleRenameSession,
      handleTogglePinSession,
    ],
  );

  return (
    <ChatSessionContext.Provider value={value}>
      {children}
    </ChatSessionContext.Provider>
  );
}

export function useChatSession() {
  const ctx = useContext(ChatSessionContext);
  if (!ctx) throw new Error("ChatSessionProvider required");
  return ctx;
}
