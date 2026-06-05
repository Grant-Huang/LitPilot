export type HelpPageId =
  | "quick-start"
  | "research-brief"
  | "artifact-panel"
  | "multi-turn"
  | "tavily-search"
  | "settings-guide"
  | "tech-stack"
  | "faq";

export type HelpCategory = "入门" | "写作" | "配置" | "参考" | "疑难";

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
  "参考",
  "疑难",
];

/** [[page-id|label]] internal help links */
export const HELP_LINK_RE = /\[\[([a-z-]+)\|([^\]]+)\]\]/g;
