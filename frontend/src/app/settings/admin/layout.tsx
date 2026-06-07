"use client";

import { SettingOutlined } from "@ant-design/icons";
import { usePathname } from "next/navigation";
import { FunctionalDocShell } from "@/components/layout/FunctionalDocShell";
import { buildAdminNavGroups, getAdminSectionMeta } from "./_shellConfig";

export default function AdminSettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const meta = getAdminSectionMeta(pathname);
  const navGroups = buildAdminNavGroups(pathname);

  return (
    <FunctionalDocShell
      brandIcon={<SettingOutlined aria-hidden />}
      brandTitle="管理员配置"
      navAriaLabel="管理员设置分类"
      navGroups={navGroups}
      pageTitle={meta.title || undefined}
      pageSummary={meta.summary || undefined}
      contentClassName="settings-doc-content"
    >
      {children}
    </FunctionalDocShell>
  );
}
