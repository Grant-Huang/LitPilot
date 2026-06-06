import { describe, expect, it } from "vitest";
import {
  buildSearchProgressTree,
  sourceStatusLabel,
  topicDisplayTitle,
  topicStatusLabel,
} from "./searchProgressTree";

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
          max_results: 20,
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
          hits: 30,
          hits_found: 30,
          hits_taken: 20,
          max_results: 20,
          top_urls: ["https://example.com/a"],
        },
      },
      {
        name: "literature_search_pass_done",
        data: {
          pass_index: 1,
          pass_total: 2,
          hits: 5,
          hits_taken: 5,
          topic_title: "AI-native MOM 定义",
          source_counts: { openalex: 30 },
        },
      },
    ];

    const tree = buildSearchProgressTree(extensions, subTopics);
    expect(tree.totalTopics).toBe(2);
    expect(tree.topics[0]?.topicTitle).toBe("AI-native MOM 定义");
    expect(tree.topics[0]?.status).toBe("done");
    expect(tree.topics[0]?.hits).toBe(5);
    expect(tree.topics[0]?.sources[0]?.hitsFound).toBe(30);
    expect(tree.topics[0]?.sources[0]?.hitsTaken).toBe(20);
    expect(sourceStatusLabel(tree.topics[0]!.sources[0]!)).toBe(
      "检索完成 · 搜到 30 篇，取 20 篇",
    );
    expect(topicStatusLabel(tree.topics[0]!)).toBe("检索完成 · 5 篇");
    expect(topicDisplayTitle(tree.topics[0]!)).toBe("AI-native MOM 定义");
  });

  it("marks failed sources as error with strikethrough state", () => {
    const extensions = [
      {
        name: "literature_search_source_done",
        data: {
          pass_index: 1,
          pass_total: 1,
          source: "pubmed",
          label: "PubMed",
          hits: 0,
          hits_found: 0,
          hits_taken: 0,
          failed: true,
          query: "test query",
        },
      },
    ];
    const tree = buildSearchProgressTree(extensions);
    const pubmed = tree.topics[0]?.sources.find((s) => s.source === "pubmed");
    expect(pubmed?.status).toBe("error");
    expect(pubmed?.failed).toBe(true);
    expect(sourceStatusLabel(pubmed!)).toBe("检索超时/失败（0）");
  });

  it("shows running topic with source completion count", () => {
    const extensions = [
      {
        name: "literature_search_pass_start",
        data: { pass_index: 1, pass_total: 1, query: "q1", topic_title: "T1" },
      },
      {
        name: "literature_search_source_done",
        data: {
          pass_index: 1,
          pass_total: 1,
          source: "openalex",
          label: "OpenAlex",
          hits_found: 5,
          hits_taken: 5,
        },
      },
    ];
    const tree = buildSearchProgressTree(extensions);
    expect(topicStatusLabel(tree.topics[0]!)).toBe(
      "检索中 · 1/5 源（1 个数据源已完成）",
    );
  });
});
