import type { DocShellNavGroup } from "@/components/layout/FunctionalDocShell";

export const ADMIN_SECTIONS = [
  {
    href: "/settings/admin",
    id: "overview",
    label: "概览",
    group: "system",
    title: "概览",
    summary: "系统就绪状态与关键能力摘要，点击行可跳转至对应配置。",
  },
  {
    href: "/settings/admin/storage",
    id: "storage",
    label: "存储",
    group: "system",
    title: "持久化存储",
    summary: "Turso 连接与运行期覆盖；冷启动仍依赖环境变量。",
  },
  {
    href: "/settings/admin/credentials",
    id: "credentials",
    label: "凭据",
    group: "connect",
    title: "凭据",
    summary: "Tavily、Jina、LLM 等 API Key 与接口地址。",
  },
  {
    href: "/settings/admin/instances",
    id: "instances",
    label: "实例库",
    group: "connect",
    title: "实例库",
    summary: "模型实例：绑定凭据与 model 名称，供能力引用。",
  },
  {
    href: "/settings/admin/capabilities",
    id: "capabilities",
    label: "能力绑定",
    group: "capability",
    title: "能力绑定",
    summary: "检索、抓取、编排与综述等能力与凭据/实例的挂载关系。",
  },
  {
    href: "/settings/admin/prompts",
    id: "prompts",
    label: "提示词",
    group: "capability",
    title: "提示词与生成策略",
    summary: "综述模板、分章策略与后处理等行为配置。",
  },
] as const;

const GROUP_LABELS: Record<string, string> = {
  system: "系统",
  connect: "连接",
  capability: "能力",
};

export function getAdminSectionMeta(pathname: string): { title: string; summary: string } {
  const section = ADMIN_SECTIONS.find((s) => s.href === pathname);
  if (section) {
    return { title: section.title, summary: section.summary };
  }
  return {
    title: "管理员配置",
    summary: "系统级配置，影响所有会话。",
  };
}

export function buildAdminNavGroups(pathname: string): DocShellNavGroup[] {
  const groups = new Map<string, DocShellNavGroup>();

  for (const section of ADMIN_SECTIONS) {
    if (!groups.has(section.group)) {
      groups.set(section.group, {
        id: section.group,
        label: GROUP_LABELS[section.group],
        items: [],
      });
    }
    groups.get(section.group)!.items.push({
      id: section.id,
      label: section.label,
      href: section.href,
      active: pathname === section.href,
    });
  }

  return ["system", "connect", "capability"]
    .map((id) => groups.get(id))
    .filter((g): g is DocShellNavGroup => Boolean(g));
}
