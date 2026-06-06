import type { DocShellNavGroup } from "@/components/layout/FunctionalDocShell";

export const PERSONAL_SECTION = {
  id: "preferences",
  label: "个人偏好",
  title: "个人偏好",
  summary: "仅影响本机个人偏好，不包含系统级密钥与能力配置。",
} as const;

export function buildPersonalNavGroups(): DocShellNavGroup[] {
  return [
    {
      id: "personal",
      label: "账户",
      items: [
        {
          id: PERSONAL_SECTION.id,
          label: PERSONAL_SECTION.label,
          active: true,
        },
      ],
    },
  ];
}
