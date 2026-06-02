import type { HelpPage, HelpPageId } from "./types";
import {
  artifactPanelPage,
  faqPage,
  multiTurnPage,
  quickStartPage,
  researchBriefPage,
  settingsGuidePage,
  tavilySearchPage,
} from "./pages";

export const HELP_PAGES: HelpPage[] = [
  quickStartPage,
  researchBriefPage,
  artifactPanelPage,
  multiTurnPage,
  tavilySearchPage,
  settingsGuidePage,
  faqPage,
];

export const HELP_PAGE_MAP: Record<HelpPageId, HelpPage> = Object.fromEntries(
  HELP_PAGES.map((p) => [p.id, p]),
) as Record<HelpPageId, HelpPage>;

export const DEFAULT_HELP_PAGE_ID: HelpPageId = "quick-start";

export function getHelpPage(id: HelpPageId): HelpPage {
  return HELP_PAGE_MAP[id] ?? HELP_PAGE_MAP[DEFAULT_HELP_PAGE_ID];
}

export { HELP_CATEGORIES, HELP_LINK_RE } from "./types";
export type { HelpPage, HelpPageId, HelpCategory } from "./types";
