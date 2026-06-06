import { describe, expect, it } from "vitest";
import { buildSearchProgressTree, topicDisplayTitle } from "./searchProgressTree";

describe("buildSearchProgressTree", () => {
  it("builds topic and source hierarchy from search extensions", () => {
    const subTopics = [
      { id: "1", title: "AI-native MOM 定义", search_query: "q1" },
      { id: "2", title: "知识图谱", search_query: "q2" },
    ];
    const extensions = [
      {
        name: "literature_search_plan",
        data: { queries: ["q1", "q2"], total_passes: 2 },
      },
      {
        name: "literature_search_pass_start",
        data: {
          pass_index: 1,
          pass_total: 2,
          query: "q1",
          topic_title: "AI-native MOM 定义",
        },
      },
      {
        name: "literature_search_source_start",
        data: {
          pass_index: 1,
          pass_total: 2,
          source: "openalex",
          label: "OpenAlex",
          expected: 8,
          query: "q1",
        },
      },
      {
        name: "literature_search_source_done",
        data: {
          pass_index: 1,
          pass_total: 2,
          source: "openalex",
          label: "OpenAlex",
          hits: 3,
          expected: 8,
          top_urls: ["https://example.com/a"],
        },
      },
      {
        name: "literature_search_pass_done",
        data: {
          pass_index: 1,
          pass_total: 2,
          hits: 5,
          topic_title: "AI-native MOM 定义",
          source_counts: { openalex: 3 },
        },
      },
    ];

    const tree = buildSearchProgressTree(extensions, subTopics);
    expect(tree.totalTopics).toBe(2);
    expect(tree.topics[0]?.topicTitle).toBe("AI-native MOM 定义");
    expect(tree.topics[0]?.status).toBe("done");
    expect(tree.topics[0]?.hits).toBe(5);
    expect(tree.topics[0]?.sources[0]?.topUrls[0]).toBe("https://example.com/a");
    expect(topicDisplayTitle(tree.topics[0]!)).toBe("AI-native MOM 定义");
  });
});
