/** 综述展示：压缩参考文献区块，引导用户使用右侧文献面板 */

const REF_HEADING =
  /^(#{1,3}\s*|[IVXLC]+\.\s*)?(?:references|参考文献|REFERENCES|References)\s*$/i;

export function collapseReviewReferences(markdown: string): string {
  if (!markdown.trim()) return markdown;
  const lines = markdown.split("\n");
  let refStart = -1;
  for (let i = 0; i < lines.length; i += 1) {
    if (REF_HEADING.test(lines[i].trim())) {
      refStart = i;
      break;
    }
  }
  if (refStart < 0) return markdown;

  let refEnd = lines.length;
  for (let i = refStart + 1; i < lines.length; i += 1) {
    const t = lines[i].trim();
    if (/^#{1,2}\s+\S/.test(t) || /^[IVXLC]+\.\s+\S/i.test(t)) {
      refEnd = i;
      break;
    }
  }

  const note =
    "> 参考文献条目已收录至右侧 **文献** 面板。请点击 Tab「文献」或综述上方的 `[1]`、`[2]`… 查看摘要、全文与 DOI。";
  const head = lines.slice(0, refStart + 1);
  const tail = lines.slice(refEnd);
  return [...head, "", note, "", ...tail].join("\n");
}

export function reviewMarkdownForDisplay(
  markdown: string,
  options?: { collapseReferences?: boolean },
): string {
  if (options?.collapseReferences) {
    return collapseReviewReferences(markdown);
  }
  return markdown;
}
