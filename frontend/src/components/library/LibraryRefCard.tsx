"use client";

import type { KeyboardEvent, MouseEvent } from "react";
import { Dropdown, Popconfirm, message } from "antd";
import type { MenuProps } from "antd";
import type { LibraryItem } from "@/lib/libraryTypes";
import type { LibraryListDensity } from "@/lib/libraryListUtils";
import { formatAuthors, formatVenueLine } from "@/lib/libraryTypes";
import {
  CITATION_FORMAT_OPTIONS,
  formatCitationForList,
  resolveDisplayTitle,
  type CitationFormatKey,
} from "@/lib/libraryDisplay";
import { libraryApi } from "@/lib/api";
import { LibraryRefBadges } from "./LibraryRefBadges";

type Props = {
  item: LibraryItem;
  listIndex: number;
  selected?: boolean;
  density?: LibraryListDensity;
  onSelect: () => void;
  onOpenFullText?: () => void;
  onShowReviews?: () => void;
  onStarChange?: (item: LibraryItem) => void;
  onDelete?: () => void | Promise<void>;
};

function onSelectKeyDown(e: KeyboardEvent, onSelect: () => void) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    onSelect();
  }
}

export function LibraryRefCard({
  item,
  listIndex,
  selected,
  density = "comfortable",
  onSelect,
  onOpenFullText,
  onShowReviews,
  onStarChange,
  onDelete,
}: Props) {
  const title = resolveDisplayTitle(item);

  const copyMenus: MenuProps["items"] = CITATION_FORMAT_OPTIONS.map((f) => ({
    key: f.key,
    label: `复制 ${f.label}`,
    onClick: () => {
      const text = formatCitationForList(item, f.key as CitationFormatKey, listIndex);
      if (!text) {
        message.info("暂无可用引用格式");
        return;
      }
      void navigator.clipboard.writeText(text);
      message.success(`已复制 ${f.label} 引用`);
    },
  }));

  const toggleStar = async (e: MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await libraryApi.star(item.id, !item.starred);
      onStarChange?.(res.item);
    } catch {
      message.error("更新收藏失败");
    }
  };

  return (
    <li
      className={`library-ref-card library-ref-card--${density}${
        selected ? " library-ref-card--selected" : ""
      }`}
    >
      <div className="library-ref-card__main">
        <div className="library-ref-card__top">
          <div
            role="button"
            tabIndex={0}
            className="library-ref-card__select"
            onClick={onSelect}
            onKeyDown={(e) => onSelectKeyDown(e, onSelect)}
          >
            <div className="library-ref-card__title">
              <span className="library-ref-card__index">[{listIndex}]</span>
              <span className="library-ref-card__title-text">{title}</span>
            </div>
            <div className="library-ref-card__authors">{formatAuthors(item.authors)}</div>
            <div className="library-ref-card__venue">{formatVenueLine(item)}</div>
            {(item.tags || []).length > 0 && (
              <div className="library-ref-card__tags" aria-label="标签">
                {(item.tags || []).slice(0, 3).map((tag) => (
                  <span key={tag} className="library-item-tag library-item-tag--readonly">
                    {tag}
                  </span>
                ))}
                {(item.tags || []).length > 3 && (
                  <span className="library-ref-card__tags-more">
                    +{(item.tags || []).length - 3}
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="library-ref-card__actions" onClick={(e) => e.stopPropagation()}>
            <Dropdown menu={{ items: copyMenus }} trigger={["click"]}>
              <button type="button" className="library-card-action" title="复制引用">
                引用
              </button>
            </Dropdown>
            <button
              type="button"
              className={`library-card-action library-card-action--star${
                item.starred ? " library-card-action--starred" : ""
              }`}
              title={item.starred ? "取消收藏" : "收藏"}
              onClick={(e) => void toggleStar(e)}
              aria-label={item.starred ? "取消收藏" : "收藏"}
            >
              {item.starred ? "★" : "☆"}
            </button>
            {onDelete && (
              <Popconfirm
                title="从文献库删除该条？"
                description="仅移除库内记录，不影响已生成的综述文件。"
                onConfirm={() => void onDelete()}
                okText="删除"
                cancelText="取消"
              >
                <button type="button" className="library-card-action library-card-action--danger">
                  删除
                </button>
              </Popconfirm>
            )}
          </div>
        </div>
        <LibraryRefBadges
          item={item}
          onOpenDetail={(action) => {
            if (action.key === "fulltext") onOpenFullText?.();
            if (action.key === "prov") onShowReviews?.();
          }}
        />
      </div>
    </li>
  );
}
