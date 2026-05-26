/** 轻量 Markdown → HTML（综述预览，无第三方依赖） */
export function renderSimpleMarkdown(source: string): string {
  const esc = (s: string) =>
    s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const blocks = (source || "").trim().split(/\n\n+/);
  if (!blocks.length) return "";

  return blocks
    .map((block) => {
      const lines = block.split("\n");
      if (lines[0]?.startsWith("### "))
        return `<h3>${inlineMd(esc(lines[0].slice(4)))}</h3>`;
      if (lines[0]?.startsWith("## "))
        return `<h2>${inlineMd(esc(lines[0].slice(3)))}</h2>`;
      if (lines[0]?.startsWith("# "))
        return `<h1>${inlineMd(esc(lines[0].slice(2)))}</h1>`;
      if (lines.every((l) => /^[-*]\s+/.test(l.trim())))
        return `<ul>${lines
          .map((l) => `<li>${inlineMd(esc(l.replace(/^[-*]\s+/, "")))}</li>`)
          .join("")}</ul>`;
      const body = lines.map((l) => inlineMd(esc(l))).join("<br/>");
      return `<p>${body}</p>`;
    })
    .join("");
}

function inlineMd(s: string): string {
  return s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(
      /`([^`]+)`/g,
      "<code class=\"litpilot-md-inline\">$1</code>",
    );
}
