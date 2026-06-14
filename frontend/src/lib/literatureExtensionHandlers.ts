type ExtensionData = Record<string, unknown> | undefined;

type HandlerContext = {
  isChat: boolean;
  activeSessionId: string | null;
  setActiveSessionId: (id: string) => void;
  loadSessions: () => Promise<void>;
  persistActiveSession: (id: string) => void;
  /** The session ID the current stream belongs to (set before streaming starts). */
  streamingSessionId: string | null;
};

type ExtensionHandler = (
  data: ExtensionData,
  ctx: HandlerContext,
) => void;

/** 仅保留 session 绑定；其余 extension 内联到左侧 workflow 卡片，不再 toast。 */
const HANDLERS: Record<string, ExtensionHandler> = {
  session: (data, ctx) => {
    const sid = data?.session_id;
    if (typeof sid !== "string" || !sid) return;
    // Refresh the session list so titles / pinned state stay current.
    void ctx.loadSessions();
    if (sid === ctx.activeSessionId) return;
    // Only navigate to the streaming session if the user hasn't explicitly
    // switched away from it.  The client always sets activeSessionId before
    // starting the stream (LiteratureStreamContext send()), so by the time
    // this event arrives the IDs should already match.  If they don't, the
    // user intentionally navigated to a different session — don't pull them back.
    if (ctx.streamingSessionId !== null && ctx.activeSessionId !== ctx.streamingSessionId) {
      // User navigated away from the streaming session; respect their choice.
      return;
    }
    ctx.setActiveSessionId(sid);
    ctx.persistActiveSession(sid);
  },
  session_title: (_data, ctx) => {
    void ctx.loadSessions();
  },
};

export function handleLiteratureExtensionEvent(
  name: string,
  data: ExtensionData,
  ctx: HandlerContext,
): void {
  const handler = HANDLERS[name];
  if (handler) handler(data, ctx);
}
