import { describe, expect, it } from "vitest";
import {
  formatWeakSubtopicBrief,
  weakSubtopicThreshold,
  weakSubtopicsFromExtensions,
  weakSubtopicsFromTrace,
} from "./subtopicWeakHints";

describe("weakSubtopicThreshold", () => {
  it("uses max(3, 25% of per_query)", () => {
    expect(weakSubtopicThreshold(8)).toBe(3);
    expect(weakSubtopicThreshold(20)).toBe(5);
  });
});

describe("weakSubtopicsFromExtensions", () => {
  it("reads weak_subtopics from merge extension", () => {
    const hints = weakSubtopicsFromExtensions([
      {
        name: "literature_search_merge",
        data: {
          weak_subtopics: [
            { pass_index: 2, title: "子主题 B", hits_taken: 1 },
          ],
        },
      },
    ]);
    expect(hints).toEqual([
      { passIndex: 2, title: "子主题 B", hitsTaken: 1 },
    ]);
  });

  it("derives weak passes from pass_done when merge has no list", () => {
    const hints = weakSubtopicsFromExtensions(
      [
        {
          name: "literature_search_plan",
          data: { per_query_max_results: 8, queries: ["a", "b"] },
        },
        {
          name: "literature_search_pass_done",
          data: { pass_index: 1, hits_taken: 6, topic_title: "方向 A" },
        },
        {
          name: "literature_search_pass_done",
          data: { pass_index: 2, hits_taken: 1, topic_title: "方向 B" },
        },
      ],
      [{ title: "方向 A" }, { title: "方向 B" }],
    );
    expect(hints).toEqual([
      { passIndex: 2, title: "方向 B", hitsTaken: 1 },
    ]);
  });

  it("skips weak hints for single-pass search", () => {
    const hints = weakSubtopicsFromExtensions([
      {
        name: "literature_search_plan",
        data: { per_query_max_results: 8, queries: ["only"] },
      },
      {
        name: "literature_search_pass_done",
        data: { pass_index: 1, hits_taken: 0 },
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
          { passIndex: 3, title: "主题 C", hitsTaken: 2 },
        ],
      },
    });
    expect(hints).toEqual([
      { passIndex: 3, title: "主题 C", hitsTaken: 2 },
    ]);
  });
});

describe("formatWeakSubtopicBrief", () => {
  it("formats single and multiple weak subtopics", () => {
    expect(
      formatWeakSubtopicBrief([
        { passIndex: 1, title: "A", hitsTaken: 1 },
      ]),
    ).toContain("expand_search");
    expect(
      formatWeakSubtopicBrief([
        { passIndex: 1, title: "A", hitsTaken: 1 },
        { passIndex: 2, title: "B", hitsTaken: 0 },
      ]),
    ).toContain("expand_search");
  });
});
