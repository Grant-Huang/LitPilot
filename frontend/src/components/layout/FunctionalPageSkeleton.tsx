"use client";

type Props = {
  title: string;
  subtitle?: string;
  rows?: number;
  className?: string;
};

export function FunctionalPageSkeleton({
  title,
  subtitle = "加载中…",
  rows = 6,
  className = "",
}: Props) {
  return (
    <div className={`functional-shell functional-page-skeleton ${className}`.trim()}>
      <header className="functional-page__header">
        <div className="functional-page__header-row">
          <div>
            <h1>{title}</h1>
            <p className="functional-page__subtitle">{subtitle}</p>
          </div>
        </div>
      </header>
      <div className="functional-page__body">
        <div className="functional-page__inner functional-page-skeleton__inner">
          <ul className="functional-page-skeleton__list" aria-hidden="true">
            {Array.from({ length: rows }, (_, i) => (
              <li key={i} className="functional-page-skeleton__row" />
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
