import { describe, expect, it } from "vitest";
import type { LibraryItem } from "@/lib/libraryTypes";
import {
  extractAbstractFromFullText,
  formatCitationForList,
  looksLikeAbstract,
  resolveAbstractText,
  resolveDisplayTitle,
} from "@/lib/libraryDisplay";

const base: LibraryItem = {
  id: "x",
  display_index: 5,
  title: "https://example.com/paper",
  authors: [],
  url: "https://example.com/research-paper.pdf",
  availability: {},
  citations: { apa: "[5] Author (2024). Title." },
};

describe("libraryDisplay", () => {
  it("resolveDisplayTitle from url path", () => {
    expect(resolveDisplayTitle(base)).toBe("research paper");
  });

  it("formatCitationForList renumbers", () => {
    expect(formatCitationForList(base, "apa", 2)).toBe("[2] Author (2024). Title.");
  });

  it("looksLikeAbstract rejects url-like junk", () => {
    expect(looksLikeAbstract("https://foo.bar/x")).toBe(false);
    expect(
      looksLikeAbstract(
        "This paper studies industrial software with AI-native architectures in depth.",
      ),
    ).toBe(true);
  });

  it("extractAbstractFromFullText finds section", () => {
    const md = "# Title\n\n## Abstract\n\nWe propose a new method.\n\n## Intro\n\nMore.";
    expect(extractAbstractFromFullText(md)).toContain("We propose");
  });

  it("resolveAbstractText prefers clean field", () => {
    const item = {
      ...base,
      title: "T",
      abstract: "A valid abstract that is long enough to pass the heuristic check easily.",
    };
    const r = resolveAbstractText(item, "# junk\n\n## Abstract\n\nFrom web.");
    expect(r.source).toBe("field");
  });
});
