import { HELP_LINK_RE, type HelpPageId } from "./types";

const VALID_HELP_PAGE_IDS = new Set<HelpPageId>([
  "quick-start",
  "research-brief",
  "artifact-panel",
  "multi-turn",
  "tavily-search",
  "settings-guide",
  "clarification",
  "tech-stack",
  "faq",
]);

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineMdEscaped(s: string): string {
  return escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(
      /`([^`]+)`/g,
      '<code class="litpilot-md-inline">$1</code>',
    );
}

/** Preserve pre-inserted inline link buttons while escaping surrounding text. */
function inlineMdWithEmbeddedHtml(s: string): string {
  const parts = s.split(/(<button[\s\S]*?<\/button>)/g);
  return parts
    .map((part) => {
      if (part.startsWith("<button")) return part;
      return inlineMdEscaped(part);
    })
    .join("");
}

function helpLinkButton(pageId: string, label: string): string {
  const id = escapeHtml(pageId);
  const text = escapeHtml(label);
  if (!VALID_HELP_PAGE_IDS.has(pageId as HelpPageId)) {
    return text;
  }
  return `<button type="button" class="help-center__inline-link" data-help-page="${id}">${text}</button>`;
}

function injectHelpLinks(source: string): string {
  return source.replace(HELP_LINK_RE, (_m, id: string, label: string) =>
    helpLinkButton(id, label),
  );
}

function renderMarkdownTable(block: string): string {
  const rows = block
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("|") && l.endsWith("|"));
  const dataRows = rows.filter((r) => !/^\|[\s\-:|]+\|$/.test(r));
  if (!dataRows.length) {
    return `<p>${inlineMdWithEmbeddedHtml(block.trim())}</p>`;
  }
  const cells = dataRows.map((r) =>
    r
      .slice(1, -1)
      .split("|")
      .map((c) => c.trim()),
  );
  const [head, ...body] = cells;
  const th = head
    .map((c) => `<th>${inlineMdWithEmbeddedHtml(c)}</th>`)
    .join("");
  const tb = body
    .map(
      (row) =>
        `<tr>${row.map((c) => `<td>${inlineMdWithEmbeddedHtml(c)}</td>`).join("")}</tr>`,
    )
    .join("");
  return `<div class="help-center__table-wrap"><table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table></div>`;
}

function renderFencedCode(block: string): string {
  const lines = block.split("\n");
  const code = lines
    .slice(1, lines[lines.length - 1] === "```" ? -1 : undefined)
    .join("\n");
  return `<pre class="help-center__pre"><code>${escapeHtml(code)}</code></pre>`;
}

/** Render full help page body as one HTML document (inline links stay in paragraph flow). */
export function renderHelpBodyHtml(body: string): string {
  const linked = injectHelpLinks((body || "").trim());
  if (!linked) return "";

  const blocks = linked.split(/\n\n+/);
  return blocks
    .map((block) => {
      const trimmed = block.trim();
      if (!trimmed) return "";
      if (trimmed.startsWith("```")) {
        return renderFencedCode(trimmed);
      }
      const lines = trimmed.split("\n");
      if (lines[0]?.startsWith("### ")) {
        return `<h3>${inlineMdWithEmbeddedHtml(lines[0].slice(4))}</h3>`;
      }
      if (lines[0]?.startsWith("## ")) {
        return `<h2>${inlineMdWithEmbeddedHtml(lines[0].slice(3))}</h2>`;
      }
      if (lines[0]?.startsWith("# ")) {
        return `<h2 class="help-center__body-title">${inlineMdWithEmbeddedHtml(lines[0].slice(2))}</h2>`;
      }
      if (lines.every((l) => /^[-*]\s+/.test(l.trim()))) {
        return `<ul>${lines
          .map(
            (l) =>
              `<li>${inlineMdWithEmbeddedHtml(l.replace(/^[-*]\s+/, "").trim())}</li>`,
          )
          .join("")}</ul>`;
      }
      if (trimmed.includes("|") && /^\|.+\|/m.test(trimmed)) {
        return renderMarkdownTable(trimmed);
      }
      const bodyHtml = lines
        .map((l) => inlineMdWithEmbeddedHtml(l))
        .join("<br/>");
      return `<p>${bodyHtml}</p>`;
    })
    .join("");
}

/** @deprecated use renderHelpBodyHtml — kept for tests that split links */
export type HelpBodyPart =
  | { kind: "markdown"; text: string }
  | { kind: "link"; id: HelpPageId; label: string };

export function splitHelpBody(body: string): HelpBodyPart[] {
  const parts: HelpBodyPart[] = [];
  let last = 0;
  const re = new RegExp(HELP_LINK_RE.source, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) {
    if (m.index > last) {
      parts.push({ kind: "markdown", text: body.slice(last, m.index) });
    }
    parts.push({
      kind: "link",
      id: m[1] as HelpPageId,
      label: m[2],
    });
    last = m.index + m[0].length;
  }
  if (last < body.length) {
    parts.push({ kind: "markdown", text: body.slice(last) });
  }
  return parts;
}
