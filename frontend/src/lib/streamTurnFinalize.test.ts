import { describe, expect, it } from "vitest";
import { sessionHasAssistantReply } from "./streamTurnFinalize";

describe("sessionHasAssistantReply", () => {
  it("requires assistant after matching user turn", () => {
    const msgs = [
      { role: "user", content: "q1" },
      { role: "assistant", content: "a1" },
      { role: "user", content: "q2" },
    ];
    expect(sessionHasAssistantReply(msgs, "q1")).toBe(true);
    expect(sessionHasAssistantReply(msgs, "q2")).toBe(false);
  });

  it("returns false when only user exists", () => {
    expect(sessionHasAssistantReply([{ role: "user", content: "q" }], "q")).toBe(
      false,
    );
  });
});
