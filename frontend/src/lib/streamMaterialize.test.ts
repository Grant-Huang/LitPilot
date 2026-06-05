import { describe, expect, it } from "vitest";
import { createInitialStreamState } from "@meso.ai/ui";
import { materializeAssistantFromStream } from "./streamMaterialize";

describe("materializeAssistantFromStream", () => {
  it("从流状态物化 assistant 消息（含 execution trace）", () => {
    const stream = createInitialStreamState();
    stream.status = "done";
    stream.stages = [{ name: "大纲规划", state: "done" }];
    stream.textContent = "请确认大纲后继续生成。";

    const msg = materializeAssistantFromStream(stream);
    expect(msg?.role).toBe("assistant");
    expect(msg?.content).toContain("确认大纲");
    expect(msg?.extras?.executionTrace?.stages[0]?.name).toBe("大纲规划");
  });

  it("idle 状态返回 null", () => {
    const stream = createInitialStreamState();
    expect(materializeAssistantFromStream(stream)).toBeNull();
  });
});
