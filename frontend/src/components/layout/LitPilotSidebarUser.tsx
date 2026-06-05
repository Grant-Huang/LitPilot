"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Dropdown, Modal, message } from "antd";
import type { MenuProps } from "antd";
import {
  InfoCircleOutlined,
  LogoutOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { helpCenterHref } from "@/lib/helpUrl";

const USER_NAME_KEY = "litpilot:user-name";
const ACTIVE_SESSION_KEY = "litpilot:active-session";
const ARTIFACT_KEY = "litpilot:artifact-visible";

export function LitPilotSidebarUser() {
  const router = useRouter();
  const pathname = usePathname();
  const [userName, setUserName] = useState("研究员");
  const [infoOpen, setInfoOpen] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(USER_NAME_KEY);
      if (stored?.trim()) setUserName(stored.trim());
    } catch {
      /* ignore */
    }
  }, []);

  const handleLogout = useCallback(() => {
    Modal.confirm({
      title: "退出",
      content: "将清除本机会话偏好（当前选中会话等），不会删除服务端已保存的综述数据。",
      okText: "退出",
      cancelText: "取消",
      onOk: () => {
        try {
          localStorage.removeItem(ACTIVE_SESSION_KEY);
          localStorage.removeItem(ARTIFACT_KEY);
        } catch {
          /* ignore */
        }
        message.success("已退出");
        if (pathname !== "/chat") {
          router.push("/chat");
        } else {
          window.location.reload();
        }
      },
    });
  }, [pathname, router]);

  const menuItems: MenuProps["items"] = [
    {
      key: "help",
      icon: <QuestionCircleOutlined />,
      label: "帮助中心",
      onClick: () => {
        window.open(helpCenterHref(), "_blank", "noopener,noreferrer");
      },
    },
    {
      key: "info",
      icon: <InfoCircleOutlined />,
      label: "用户信息",
      onClick: () => setInfoOpen(true),
    },
    {
      key: "settings-personal",
      icon: <SettingOutlined />,
      label: "个人设置",
      onClick: () => router.push("/settings/personal"),
    },
    {
      key: "settings-admin",
      icon: <SettingOutlined />,
      label: "管理员配置",
      onClick: () => router.push("/settings/admin/credentials"),
    },
    { type: "divider" },
    {
      key: "logout",
      icon: <LogoutOutlined />,
      label: "退出",
      danger: true,
      onClick: handleLogout,
    },
  ];

  return (
    <>
      <Dropdown
        menu={{ items: menuItems }}
        placement="topLeft"
        trigger={["click"]}
        classNames={{ root: "litpilot-sidebar-user__dropdown" }}
      >
        <button type="button" className="litpilot-sidebar-user" aria-label="用户菜单">
          <span className="litpilot-sidebar-user__avatar" aria-hidden>
            <UserOutlined />
          </span>
          <span className="litpilot-sidebar-user__meta">
            <span className="litpilot-sidebar-user__name">{userName}</span>
            <span className="litpilot-sidebar-user__hint">本地模式</span>
          </span>
          <span className="litpilot-sidebar-user__chevron" aria-hidden>
            ▴
          </span>
        </button>
      </Dropdown>

      <Modal
        title="用户信息"
        open={infoOpen}
        onCancel={() => setInfoOpen(false)}
        onOk={() => {
          const trimmed = userName.trim() || "研究员";
          setUserName(trimmed);
          try {
            localStorage.setItem(USER_NAME_KEY, trimmed);
          } catch {
            /* ignore */
          }
          setInfoOpen(false);
          message.success("已保存显示名称");
        }}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--color-text-muted)" }}>
          LitPilot 当前为本地文件存储，无账号登录。此处名称仅用于侧栏展示。
        </p>
        <label className="label" htmlFor="litpilot-user-name">
          显示名称
        </label>
        <input
          id="litpilot-user-name"
          className="input"
          value={userName}
          onChange={(e) => setUserName(e.target.value)}
          placeholder="研究员"
          style={{ marginTop: 6, width: "100%" }}
        />
      </Modal>
    </>
  );
}
