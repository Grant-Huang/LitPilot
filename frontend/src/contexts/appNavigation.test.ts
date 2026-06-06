import { describe, expect, it } from "vitest";
import { pendingNavLabel } from "@/contexts/AppNavigationContext";

describe("pendingNavLabel", () => {
  it("appends ellipsis when href matches pending", () => {
    expect(pendingNavLabel("/library", "文献库", "/library")).toBe("文献库 …");
  });

  it("keeps label when another route is pending", () => {
    expect(pendingNavLabel("/library", "文献库", "/settings/admin")).toBe("文献库");
  });
});
