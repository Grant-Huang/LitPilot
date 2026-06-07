import { describe, expect, it } from "vitest";
import {
  buildSearchProgressTree,
  subtopicDisplayTitle,
  subtopicStatusLabel,
} from "./searchProgressTree";

describe("buildSearchProgressTree", () => {
  it("builds subtopic three-phase tree from v2 extensions", () => {
    const extensions = [
      {
        name: "literature_subtopic_plan",
        data: {
          subtopics: [
            { id: "st1", title: "AI-native MOM 定义", search_query: "q1" },
            { id: "st2", title: "知识图谱", search_query: "q2" },
          ],
        },
      },
      {
        name: "literature_subtopic_search_done",
        data: { subtopic_id: "st1", raw_count: 30, duration_ms: 1200 },
      },
      {
        name: "literature_subtopic_filter_done",
        data: { subtopic_id: "st1", kept_count: 5 },
      },
      {
        name: "literature_subtopic_fetch_done",
        data: { subtopic_id: "st1", ok: 4, failed: 1, skipped: 0 },
      },
    ];

    const tree = buildSearchProgressTree(extensions);
    expect(tree.totalSubtopics).toBe(2);
    expect(tree.completedSubtopics).toBe(1);
    expect(tree.allDone).toBe(false);

    const st1 = tree.subtopics.find((s) => s.id === "st1");
    expect(st1?.title).toBe("AI-native MOM 定义");
    expect(st1?.search.detail).toBe("命中 30 篇");
    expect(st1?.filter.detail).toBe("保留 5 篇");
    expect(st1?.fetch.detail).toBe("成功 4 · 失败 1");
    expect(subtopicDisplayTitle(st1!)).toBe("AI-native MOM 定义");
    expect(subtopicStatusLabel(st1!)).toContain("成功 4");
  });

  it("marks all done when every subtopic completes fetch", () => {
    const extensions = [
      {
        name: "literature_subtopic_plan",
        data: { subtopics: [{ id: "st1", title: "T1", search_query: "q1" }] },
      },
      {
        name: "literature_subtopic_search_done",
        data: { subtopic_id: "st1", raw_count: 10 },
      },
      {
        name: "literature_subtopic_filter_done",
        data: { subtopic_id: "st1", kept_count: 3 },
      },
      {
        name: "literature_subtopic_fetch_done",
        data: { subtopic_id: "st1", ok: 3, failed: 0, skipped: 0 },
      },
    ];
    const tree = buildSearchProgressTree(extensions);
    expect(tree.allDone).toBe(true);
    expect(tree.completedSubtopics).toBe(1);
  });
});
