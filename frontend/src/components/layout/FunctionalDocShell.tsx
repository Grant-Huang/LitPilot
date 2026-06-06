"use client";

import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";

export type DocShellNavItem = {
  id: string;
  label: string;
  href?: string;
  onClick?: () => void;
  active?: boolean;
};

export type DocShellNavGroup = {
  id: string;
  label?: string;
  items: DocShellNavItem[];
};

type FunctionalDocShellProps = {
  brandIcon?: ReactNode;
  brandTitle: string;
  navGroups: DocShellNavGroup[];
  navAriaLabel?: string;
  pageTitle?: string;
  pageSummary?: string;
  children: ReactNode;
  className?: string;
  mainClassName?: string;
  contentClassName?: string;
};

function DocShellNavItem({ item }: { item: DocShellNavItem }) {
  const className = clsx(
    "functional-doc-shell__nav-item",
    item.active && "functional-doc-shell__nav-item--active",
  );

  if (item.href) {
    return (
      <Link href={item.href} className={className} aria-current={item.active ? "page" : undefined}>
        {item.label}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className={className}
      aria-current={item.active ? "page" : undefined}
      onClick={item.onClick}
    >
      {item.label}
    </button>
  );
}

export function FunctionalDocShell({
  brandIcon,
  brandTitle,
  navGroups,
  navAriaLabel = "页面目录",
  pageTitle,
  pageSummary,
  children,
  className,
  mainClassName,
  contentClassName,
}: FunctionalDocShellProps) {
  const showPageHeader = Boolean(pageTitle || pageSummary);

  return (
    <div className={clsx("functional-doc-shell", className)}>
      <header className="functional-doc-shell__header">
        <h1 className="functional-doc-shell__brand">
          {brandIcon}
          {brandTitle}
        </h1>
      </header>

      <div className="functional-doc-shell__body">
        <nav className="functional-doc-shell__nav" aria-label={navAriaLabel}>
          {navGroups.map((group) => (
            <div key={group.id} className="functional-doc-shell__nav-group">
              {group.label ? (
                <span className="functional-doc-shell__nav-cat">{group.label}</span>
              ) : null}
              <ul className="functional-doc-shell__nav-list">
                {group.items.map((item) => (
                  <li key={item.id}>
                    <DocShellNavItem item={item} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className={clsx("functional-doc-shell__main", mainClassName)}>
          {showPageHeader ? (
            <header className="functional-doc-shell__page-header">
              {pageTitle ? <h2 className="functional-doc-shell__page-title">{pageTitle}</h2> : null}
              {pageSummary ? <p className="functional-doc-shell__page-summary">{pageSummary}</p> : null}
            </header>
          ) : null}
          <div className={clsx("functional-doc-shell__content", contentClassName)}>{children}</div>
        </div>
      </div>
    </div>
  );
}
