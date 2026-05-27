import { describe, expect, it } from "vitest";
import {
  streamHasArtifactPane,
  streamStateWithMatrix,
  streamStateWithReview,
} from "./buildArtifactStream";

describe("buildArtifactStream", () => {
  it("creates review artifact stream state", () => {
    const state = streamStateWithReview("# Review");
    expect(streamHasArtifactPane(state)).toBe(true);
    expect(state.artifacts["review-saved"].lang).toBe("markdown");
  });

  it("creates matrix artifact stream state", () => {
    const state = streamStateWithMatrix("# Matrix");
    expect(streamHasArtifactPane(state)).toBe(true);
    expect(state.artifacts["matrix-saved"].lang).toBe(
      "literature-matrix+markdown",
    );
  });
});
