"use client";

import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";

export default function AdminSettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const tabs = [
    { id: "overview", label: "概览", href: "/settings/admin" },
    { id: "storage", label: "存储", href: "/settings/admin/storage" },
    { id: "credentials", label: "凭据", href: "/settings/admin/credentials" },
    { id: "instances", label: "实例库", href: "/settings/admin/instances" },
    { id: "capabilities", label: "能力绑定", href: "/settings/admin/capabilities" },
    { id: "prompts", label: "提示词", href: "/settings/admin/prompts" },
  ];

  return (
    <div className="functional-shell settings-admin-page">
      <header className="functional-page__header settings-admin-page__header">
        <div className="functional-page__inner settings-admin-page__inner">
          <div className="card settings-section settings-admin-page__head-card">
            <div>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>管理员配置</h2>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
                系统级配置，影响所有会话。
              </p>
            </div>

            <div className="settings-tabs" role="tablist" aria-label="管理员设置分类" style={{ padding: 0, border: 0 }}>
              {tabs.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={pathname === t.href}
                  className={clsx("settings-tabs__btn", pathname === t.href && "settings-tabs__btn--active")}
                  onClick={() => router.push(t.href)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <div className="functional-page__body">
        <div className="functional-page__inner settings-admin-page__inner">{children}</div>
      </div>
    </div>
  );
}
