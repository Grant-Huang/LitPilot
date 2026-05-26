"use client";

import type { LibraryItem } from "@/lib/libraryTypes";
import type { LibraryListDensity } from "@/lib/libraryListUtils";
import { formatAuthors, formatVenueLine } from "@/lib/libraryTypes";
import { LibraryRefBadges } from "./LibraryRefBadges";

type Props = {
  item: LibraryItem;
  selected?: boolean;
  density?: LibraryListDensity;
  onSelect: () => void;
  onOpenFullText?: () => void;
};

export function LibraryRefCard({
  item,
  selected,
  density = "comfortable",
  onSelect,
  onOpenFullText,
}: Props) {
  return (
    <li
      className={`library-ref-card library-ref-card--${density}${
        selected ? " library-ref-card--selected" : ""
      }`}
    >
      <button type="button" className="library-ref-card__main" onClick={onSelect}>
        <div className="library-ref-card__title">
          <span className="library-ref-card__index">[{item.display_index}]</span>
          <span className="library-ref-card__title-text">{item.title}</span>
          {item.starred && (
            <span className="library-ref-card__star" aria-label="已收藏">
              ★
            </span>
          )}
        </div>
        <div className="library-ref-card__authors">{formatAuthors(item.authors)}</div>
        <div className="library-ref-card__venue">{formatVenueLine(item)}</div>
        <LibraryRefBadges
          item={item}
          onOpenDetail={(action) => {
            if (action.key === "fulltext") onOpenFullText?.();
          }}
        />
      </button>
    </li>
  );
}
