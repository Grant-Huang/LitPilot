import { DEFAULT_HELP_PAGE_ID, type HelpPageId } from "@/content/help";

/** 帮助中心独立页 URL（侧栏菜单用新标签打开） */
export function helpCenterHref(pageId: HelpPageId = DEFAULT_HELP_PAGE_ID): string {
  if (pageId === DEFAULT_HELP_PAGE_ID) return "/help";
  return `/help?page=${encodeURIComponent(pageId)}`;
}
