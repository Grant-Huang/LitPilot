"use client";

import { useState } from "react";

type SubTopic = {
  id?: string;
  title?: string;
  search_query?: string;
};

type Props = {
  subTopics: SubTopic[];
};

export function SubtopicListView({ subTopics }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);

  if (!subTopics.length) return null;

  return (
    <ul className="litpilot-subtopic-list">
      {subTopics.map((st, i) => {
        const id = st.id ?? `sub-${i}`;
        const title = (st.title ?? "").trim() || `子主题 ${i + 1}`;
        const expanded = openId === id;
        return (
          <li key={id} className="litpilot-subtopic-list__item">
            <button
              type="button"
              className="litpilot-subtopic-list__head"
              onClick={() => setOpenId(expanded ? null : id)}
              aria-expanded={expanded}
            >
              <span className="litpilot-subtopic-list__title">{title}</span>
            </button>
            {expanded && st.search_query ? (
              <p className="litpilot-subtopic-list__query">{st.search_query}</p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
