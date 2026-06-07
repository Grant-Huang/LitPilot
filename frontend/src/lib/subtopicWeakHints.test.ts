import { describe, expect, it } from "vitest";
import {
  formatWeakSubtopicBrief,
  weakSubtopicThreshold,
  weakSubtopicsFromExtensions,
  weakSubtopicsFromTrace,
} from "./subtopicWeakHints";

describe("weakSubtopicThreshold", () => {
  it("returns fixed threshold", () => {
    expect(weakSubtopicThreshold(8)).toBe(3);
    expect(weakSubtopicThreshold(20)).toBe(3);
  });
});

describe("weakSubtopicsFromExtensions", () => {
  it("derives weak subtopics from filter_done events", () => {
    const hints = weakSubtopicsFromExtensions(
      [
        {
          name: "literature_subtopic_filter_done",
          data: { subtopic_id: "st1", kept_count: 5 },
        },
        {
          name: "literature_subtopic_filter_done",
          data: { subtopic_id: "st2", kept_count: 1 },
        },
      ],
      [
        { id: "st1", title: "方向 A" },
        { id: "st2", title: "方向 B" },
      ],
    );
    expect(hints).toEqual([
      { subtopicId: "st2", title: "方向 B", keptCount: 1 },
    ]);
  });

  it("skips weak hints for single subtopic", () => {
    const hints = weakSubtopicsFromExtensions([
      {
        name: "literature_subtopic_filter_done",
        data: { subtopic_id: "st1", kept_count: 0 },
      },
    ]);
    expect(hints).toEqual([]);
  });
});

describe("weakSubtopicsFromTrace", () => {
  it("reads persisted literatureStats.weakSubtopics", () => {
    const hints = weakSubtopicsFromTrace({
      literatureStats: {
        weakSubtopics: [
          { subtopicId: "st3", title: "主题 C", keptCount: 2 },
        ],
      },
    });
    expect(hints).toEqual([
      { subtopicId: "st3", title: "主题 C", keptCount: 2 },
    ]);
  });
});

describe("formatWeakSubtopicBrief", () => {
  it("formats single and multiple weak subtopics", () => {
    expect(
      formatWeakSubtopicBrief([
        { subtopicId: "st1", title: "A", keptCount: 1 },
      ]),
    ).toContain("修改子主题");
    expect(
      formatWeakSubtopicBrief([
        { subtopicId: "st1", title: "A", keptCount: 1 },
        { subtopicId: "st2", title: "B", keptCount: 0 },
      ]),
    ).toContain("增加/修改子主题");
  });
});
