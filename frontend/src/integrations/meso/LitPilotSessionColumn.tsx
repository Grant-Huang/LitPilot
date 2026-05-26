"use client";

import { useState } from "react";
import {
  MoreOutlined,
  PlusOutlined,
  PushpinFilled,
  PushpinOutlined,
} from "@ant-design/icons";
import { Dropdown, Input, Modal, message } from "antd";
import type { MenuProps } from "antd";
import type { SessionMeta } from "@/lib/api";

type Props = {
  sessions: SessionMeta[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewSession: () => void;
  onDelete: (id: string) => Promise<void>;
  onRename: (id: string, title: string) => Promise<void>;
  onTogglePin: (id: string, pinned: boolean) => Promise<void>;
};

export function LitPilotSessionColumn({
  sessions,
  activeId,
  onSelect,
  onNewSession,
  onDelete,
  onRename,
  onTogglePin,
}: Props) {
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

  const openRename = (s: SessionMeta) => {
    setRenameId(s.id);
    setRenameTitle(s.title);
    setRenameOpen(true);
    setMenuOpenId(null);
  };

  const submitRename = async () => {
    const title = renameTitle.trim();
    if (!renameId || !title) {
      message.warning("标题不能为空");
      return;
    }
    try {
      await onRename(renameId, title);
      message.success("已重命名");
      setRenameOpen(false);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : String(e));
    }
  };

  const confirmDelete = (s: SessionMeta) => {
    setMenuOpenId(null);
    Modal.confirm({
      title: "删除会话",
      content: `确定删除「${s.title}」？相关消息与综述文件将一并删除，且无法恢复。`,
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        try {
          await onDelete(s.id);
          message.success("已删除");
        } catch (e: unknown) {
          message.error(e instanceof Error ? e.message : String(e));
        }
      },
    });
  };

  const menuFor = (s: SessionMeta): MenuProps["items"] => [
    {
      key: "rename",
      label: "重命名",
      onClick: () => openRename(s),
    },
    {
      key: "pin",
      label: s.pinned ? "取消置顶" : "置顶",
      icon: s.pinned ? <PushpinFilled /> : <PushpinOutlined />,
      onClick: () => {
        setMenuOpenId(null);
        void onTogglePin(s.id, !s.pinned);
      },
    },
    { type: "divider" },
    {
      key: "delete",
      label: "删除",
      danger: true,
      onClick: () => confirmDelete(s),
    },
  ];

  return (
    <div className="litpilot-session-col">
      <div className="litpilot-session-col__header">
        <span className="litpilot-session-col__title">历史会话</span>
        <button
          type="button"
          className="litpilot-session-col__icon-btn"
          onClick={onNewSession}
          title="新建会话"
          aria-label="新建会话"
        >
          <PlusOutlined />
        </button>
      </div>
      <div className="litpilot-session-col__list">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`litpilot-session-item${
              s.id === activeId ? " litpilot-session-item--active" : ""
            }${s.pinned ? " litpilot-session-item--pinned" : ""}${
              menuOpenId === s.id ? " litpilot-session-item--menu-open" : ""
            }`}
          >
            <button
              type="button"
              className="litpilot-session-item__main"
              onClick={() => onSelect(s.id)}
            >
              <div className="litpilot-session-item__title-row">
                {s.pinned && (
                  <PushpinFilled
                    className="litpilot-session-item__pin"
                    aria-label="已置顶"
                  />
                )}
                <span className="litpilot-session-item__title">{s.title}</span>
              </div>
              {s.updated_at && (
                <span className="litpilot-session-item__time">
                  {new Date(s.updated_at).toLocaleString("zh-CN", {
                    month: "numeric",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              )}
            </button>
            <Dropdown
              menu={{ items: menuFor(s) }}
              trigger={["click"]}
              open={menuOpenId === s.id}
              onOpenChange={(open) => setMenuOpenId(open ? s.id : null)}
            >
              <button
                type="button"
                className="litpilot-session-item__more"
                aria-label="会话操作"
                onClick={(e) => e.stopPropagation()}
              >
                <MoreOutlined />
              </button>
            </Dropdown>
          </div>
        ))}
        {sessions.length === 0 && (
          <p className="litpilot-session-col__empty">暂无会话，点击 + 新建</p>
        )}
      </div>

      <Modal
        title="重命名会话"
        open={renameOpen}
        onOk={() => void submitRename()}
        onCancel={() => setRenameOpen(false)}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Input
          value={renameTitle}
          onChange={(e) => setRenameTitle(e.target.value)}
          placeholder="会话标题"
          maxLength={80}
          onPressEnter={() => void submitRename()}
        />
      </Modal>
    </div>
  );
}
