import { describe, expect, it } from "vitest";
import type { StreamState } from "@meso.ai/ui";
import {
  buildStreamActivitySnapshot,
  extractStreamParallelism,
  formatParallelismChips,
  formatStreamActivityHint,
  STREAM_SILENCE_WARN_SEC,
} from "./streamActivity";

function minimalStream(partial: Partial<StreamState> = {}): StreamState {
  return {
    status: "streaming",
    textContent: "",
    thinkContent: "",
    stages: [],
    toolCalls: {},
    toolCallOrder: [],
    artifacts: {},
    artifactOrder: [],
    workflowRuns: {},
    workflowRunOrder: [],
    extensionLog: [],
    ...partial,
  } as StreamState;
}

describe("buildStreamActivitySnapshot", () => {
  it("marks waiting after silence threshold", () => {
    const now = 100_000;
    const snap = buildStreamActivitySnapshot(
      minimalStream({
        stages: [{ name: "文献检索", state: "active" }],
      }),
      now,
      now - (STREAM_SILENCE_WARN_SEC + 1) * 1000,
      now - 30_000,
    );
    expect(snap.level).toBe("waiting");
    expect(snap.silenceSec).toBeGreaterThanOrEqual(STREAM_SILENCE_WARN_SEC);
  });

  it("uses literature_progress extension for stage hint", () => {
    const now = Date.now();
    const snap = buildStreamActivitySnapshot(
      minimalStream({
        extensionLog: [
          {
            type: "extension",
            schema_version: "1.0",
            payload: {
              name: "literature_progress",
              version: "1.0",
              data: {
                stage: "fetch",
                detail: "3/10 篇",
                elapsed_ms: 12000,
                completed: 3,
                total: 10,
              },
            },
          },
        ],
      }),
      now,
      now,
      now,
    );
    expect(snap.stage).toBe("抓取全文");
    expect(formatStreamActivityHint(snap)).toContain("3/10");
  });
});

describe("extractStreamParallelism", () => {
  it("builds search and fetch chips from extension log", () => {
    const info = extractStreamParallelism([
      {
        type: "extension",
        schema_version: "1.0",
        payload: {
          name: "literature_search_plan",
          version: "1.0",
          data: {
            parallel_mode: "by_topic",
            topic_parallel: 3,
          },
        },
      },
      {
        type: "extension",
        schema_version: "1.0",
        payload: {
          name: "literature_progress",
          version: "1.0",
          data: {
            stage: "fetch",
            parallel: 4,
            in_flight: 2,
          },
        },
      },
    ] as StreamState["extensionLog"]);
    expect(formatParallelismChips(info)).toEqual([
      "检索 3 主题并行",
      "抓取 4 路并行",
    ]);
  });

  it("falls back to in_flight when parallel is missing", () => {
    const info = extractStreamParallelism([
      {
        type: "extension",
        schema_version: "1.0",
        payload: {
          name: "literature_progress",
          version: "1.0",
          data: { stage: "fetch", in_flight: 3 },
        },
      },
    ] as StreamState["extensionLog"]);
    expect(formatParallelismChips(info)).toEqual(["抓取 3 路并行"]);
  });
});
