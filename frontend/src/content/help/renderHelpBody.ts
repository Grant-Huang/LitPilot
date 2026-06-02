import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";
import { HELP_LINK_RE, type HelpPageId } from "./types";

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

export function renderHelpMarkdownChunk(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("```")) {
    const lines = trimmed.split("\n");
    const code = lines.slice(1, lines[lines.length - 1] === "```" ? -1 : undefined).join("\n");
    const esc = code
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return `<pre class="help-center__pre"><code>${esc}</code></pre>`;
  }
  if (trimmed.includes("|") && /^\|.+\|/m.test(trimmed)) {
    return renderMarkdownTable(trimmed);
  }
  return renderSimpleMarkdown(trimmed);
}

function renderMarkdownTable(block: string): string {
  const esc = (s: string) =>
    s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const rows = block
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("|") && l.endsWith("|"));
  const dataRows = rows.filter((r) => !/^\|[\s\-:|]+\|$/.test(r));
  if (!dataRows.length) return renderSimpleMarkdown(block);
  const cells = dataRows.map((r) =>
    r
      .slice(1, -1)
      .split("|")
      .map((c) => c.trim()),
  );
  const [head, ...body] = cells;
  const th = head.map((c) => `<th>${inlineMdHelp(esc(c))}</th>`).join("");
  const tb = body
    .map(
      (row) =>
        `<tr>${row.map((c) => `<td>${inlineMdHelp(esc(c))}</td>`).join("")}</tr>`,
    )
    .join("");
  return `<table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table>`;
}

function inlineMdHelp(s: string): string {
  return s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code class=\"litpilot-md-inline\">$1</code>");
}
