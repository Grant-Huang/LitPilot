export type HelpPageId =
  | "quick-start"
  | "research-brief"
  | "artifact-panel"
  | "multi-turn"
  | "tavily-search"
  | "settings-guide"
  | "clarification"
  | "tech-stack"
  | "faq";

export type HelpCategory = "入门" | "写作" | "配置" | "疑难" | "参考";

export type HelpPage = {
  id: HelpPageId;
  title: string;
  category: HelpCategory;
  summary: string;
  body: string;
  related?: HelpPageId[];
};

export const HELP_CATEGORIES: HelpCategory[] = [
  "入门",
  "写作",
  "配置",
  "疑难",
  "参考",
];

/** [[page-id|label]] internal help links */
export const HELP_LINK_RE = /\[\[([a-z-]+)\|([^\]]+)\]\]/g;
