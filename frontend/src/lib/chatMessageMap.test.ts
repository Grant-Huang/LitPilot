import { describe, expect, it } from "vitest";
import { chatMessagesToLitPilot } from "@/lib/chatMessageMap";
import type { ChatMessage } from "@/lib/api";

describe("chatMessagesToLitPilot", () => {
  it("keeps user message text regardless of delivery meta", () => {
    const msgs: ChatMessage[] = [
      { role: "user", content: "大模型在医疗诊断中的应用" },
    ];
    const mapped = chatMessagesToLitPilot(msgs);
    expect(mapped).toHaveLength(1);
    expect(mapped[0].content).toBe("大模型在医疗诊断中的应用");
  });

  it("hides process-delivery assistant text", () => {
    const msgs: ChatMessage[] = [
      {
        role: "assistant",
        content: "检索完成",
        meta: { delivery: "process" },
      },
    ];
    const mapped = chatMessagesToLitPilot(msgs);
    expect(mapped[0].content).toBe("");
  });

  it("shows chat-delivery assistant text", () => {
    const msgs: ChatMessage[] = [
      {
        role: "assistant",
        content: "请补充研究范围",
        meta: { delivery: "chat" },
      },
    ];
    const mapped = chatMessagesToLitPilot(msgs);
    expect(mapped[0].content).toBe("请补充研究范围");
  });
});
