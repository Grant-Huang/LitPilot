import type { ChatMessage } from "@/lib/api";

/** 本轮用户问题是否已在服务端落库，且其后已有助手回复 */
export function sessionHasAssistantReply(
  msgs: ChatMessage[],
  userText: string | null,
): boolean {
  if (!msgs.some((m) => m.role === "assistant")) return false;
  if (!userText) return true;
  let lastUserIdx = -1;
  for (let i = 0; i < msgs.length; i += 1) {
    if (msgs[i].role === "user" && msgs[i].content === userText) {
      lastUserIdx = i;
    }
  }
  if (lastUserIdx < 0) {
    return msgs[msgs.length - 1]?.role === "assistant";
  }
  for (let i = lastUserIdx + 1; i < msgs.length; i += 1) {
    if (msgs[i].role === "assistant") return true;
  }
  return false;
}

export const ASSISTANT_RELOAD_ATTEMPTS = 10;
export const ASSISTANT_RELOAD_BASE_MS = 150;
