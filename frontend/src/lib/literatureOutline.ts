export const LITERATURE_OUTLINE_LANG = "literature-outline+json";

export type OutlineSectionJson = {
  id: string;
  number: string;
  title: string;
  desc: string;
  sub_topic_id?: string;
  mounted_paper_ids?: string[];
  mount_hints?: { paper_id: string; key_info?: string }[];
};

export type LiteratureOutlineJson = {
  version?: number;
  topic: string;
  research_questions?: string[];
  sub_topics?: {
    id: string;
    title: string;
    description: string;
    search_query: string;
  }[];
  sections: OutlineSectionJson[];
  status?: string;
};

export function parseLiteratureOutline(content: string): LiteratureOutlineJson | null {
  const trimmed = (content || "").trim();
  if (!trimmed) return null;
  try {
    const data = JSON.parse(trimmed) as LiteratureOutlineJson;
    if (!Array.isArray(data.sections)) return null;
    return data;
  } catch {
    return null;
  }
}

export function findOutlineArtifact(
  artifacts: Record<string, { lang: string; content: string; done: boolean }>,
  order: string[],
): { id: string; outline: LiteratureOutlineJson; done: boolean } | null {
  for (let i = order.length - 1; i >= 0; i -= 1) {
    const id = order[i];
    const art = artifacts[id];
    if (!art || art.lang !== LITERATURE_OUTLINE_LANG) continue;
    const outline = parseLiteratureOutline(art.content);
    if (outline) return { id, outline, done: art.done };
  }
  return null;
}
