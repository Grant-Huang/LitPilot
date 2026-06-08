type ExtensionData = Record<string, unknown> | undefined;

type HandlerContext = {
  isChat: boolean;
  activeSessionId: string | null;
  setActiveSessionId: (id: string) => void;
  loadSessions: () => Promise<void>;
  persistActiveSession: (id: string) => void;
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
    if (sid === ctx.activeSessionId) return;
    ctx.setActiveSessionId(sid);
    ctx.persistActiveSession(sid);
    void ctx.loadSessions();
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
