"use client";

import type { LiteratureOutlineJson } from "@/lib/literatureOutline";

type Props = {
  outline: LiteratureOutlineJson;
  streaming?: boolean;
};

export function LiteratureOutlineView({ outline, streaming }: Props) {
  const subTopics = outline.sub_topics ?? [];
  const sections = outline.sections ?? [];

  return (
    <div className="literature-outline-view">
      <header className="literature-outline-view__header">
        <h3 className="literature-outline-view__topic">{outline.topic || "文献综述大纲"}</h3>
        {streaming ? (
          <span className="literature-outline-view__badge">生成中…</span>
        ) : (
          <span className="literature-outline-view__badge literature-outline-view__badge--done">
            {outline.status === "confirmed" ? "已确认" : "草稿"}
          </span>
        )}
      </header>

      {outline.research_questions && outline.research_questions.length > 0 ? (
        <section className="literature-outline-view__block">
          <h4 className="literature-outline-view__label">研究问题</h4>
          <ul className="literature-outline-view__rq">
            {outline.research_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {subTopics.length > 1 ? (
        <section className="literature-outline-view__block">
          <h4 className="literature-outline-view__label">子主题检索</h4>
          <ol className="literature-outline-view__subtopics">
            {subTopics.map((st, idx) => (
              <li key={st.id}>
                <span className="literature-outline-view__subtopic-title">
                  {idx + 1}. {st.title}
                </span>
                <span className="literature-outline-view__subtopic-query">{st.search_query}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="literature-outline-view__block">
        <h4 className="literature-outline-view__label">章节结构</h4>
        <ol className="literature-outline-view__sections">
          {sections.map((sec) => {
            const paperCount = sec.mounted_paper_ids?.length ?? 0;
            return (
              <li key={sec.id} className="literature-outline-view__section">
                <div className="literature-outline-view__section-head">
                  <span className="literature-outline-view__section-title">
                    {sec.number !== "0" && sec.number !== "99" ? `${sec.number}. ` : ""}
                    {sec.title}
                  </span>
                  {paperCount > 0 ? (
                    <span className="literature-outline-view__paper-count">
                      {paperCount} 篇挂载
                    </span>
                  ) : null}
                </div>
                {sec.desc ? (
                  <p className="literature-outline-view__section-desc">{sec.desc}</p>
                ) : null}
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
