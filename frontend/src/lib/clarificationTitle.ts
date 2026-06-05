const DEFAULT_TITLE = "LitPilot";

const CLARIFICATION_TITLE_LABELS: Record<string, string> = {
  first_turn: "待补充研究主题",
  search_zero: "检索无命中",
  outline_confirm: "待确认大纲",
};

export function setClarificationUnreadTitle(kind?: string): void {
  if (typeof document === "undefined") return;
  const label =
    kind && CLARIFICATION_TITLE_LABELS[kind]
      ? CLARIFICATION_TITLE_LABELS[kind]
      : "待回复";
  document.title = `● ${label} · ${DEFAULT_TITLE}`;
}

export function clearClarificationUnreadTitle(): void {
  if (typeof document === "undefined") return;
  document.title = DEFAULT_TITLE;
}
