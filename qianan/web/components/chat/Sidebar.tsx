"use client";

/**
 * 千岸 QianAn — 侧边栏会话列表
 *
 * 暗色主题，纯 Tailwind + lucide-react。
 */

import { Plus, Trash2, MessageSquare, Bot, Ship } from "lucide-react";
import type { Session } from "../../lib/chat-types";

interface SidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

/** 相对时间格式化 */
function timeAgo(ts: number): string {
  const diff = Date.now() - ts;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return `${days} 天前`;
}

export function Sidebar({
  sessions,
  currentSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
}: SidebarProps) {
  return (
    <aside className="flex flex-col w-64 flex-shrink-0 h-full bg-gray-900 border-r border-gray-800">
      {/* Logo */}
      <div className="h-14 px-4 flex items-center gap-2.5 border-b border-gray-800 flex-shrink-0">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center bg-gradient-to-br from-brand-400 to-brand-500 shadow-lg shadow-brand-400/20">
          <Ship size={17} className="text-white" />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-[15px] font-semibold text-gray-100">千岸</span>
          <span className="text-[10px] text-gray-500 tracking-wide">QianAn Studio</span>
        </div>
      </div>

      {/* 新对话按钮 */}
      <div className="p-3">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-1.5 text-[13px] font-medium py-2.5 rounded-xl text-white transition-all bg-gradient-to-r from-brand-500 to-brand-700 hover:from-brand-400 hover:to-brand-600 shadow-lg shadow-brand-500/20"
        >
          <Plus size={16} /> 新对话
        </button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto px-2.5 space-y-1">
        {sessions.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-gray-600 gap-2">
            <MessageSquare size={28} className="opacity-30" />
            <span className="text-xs">暂无对话记录</span>
          </div>
        )}

        {sessions.map((session) => {
          const isActive = session.id === currentSessionId;
          return (
            <div
              key={session.id}
              className="group flex items-center gap-2.5 px-2.5 py-2 rounded-xl cursor-pointer transition-all duration-150"
              style={{
                backgroundColor: isActive ? "rgba(6, 182, 212, 0.1)" : "transparent",
                boxShadow: isActive ? "inset 2px 0 0 #939b86" : "none",
              }}
              onClick={() => onSelectSession(session.id)}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = "rgba(31, 41, 55, 0.5)";
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
              }}
            >
              {/* 图标 */}
              <div className="flex-shrink-0 w-[26px] h-[26px] rounded-lg flex items-center justify-center bg-gray-800 group-hover:bg-gray-700 transition-colors">
                <Bot size={13} className={isActive ? "text-brand-400" : "text-gray-400"} />
              </div>

              {/* 标题 + 时间 */}
              <div className="flex-1 min-w-0">
                <div
                  className={`truncate text-[13px] ${
                    isActive ? "text-brand-400 font-semibold" : "text-gray-300"
                  }`}
                >
                  {session.title}
                </div>
                <div className="text-[10px] text-gray-600 truncate">
                  {timeAgo(session.createdAt)}
                </div>
              </div>

              {/* 删除按钮 */}
              <button
                className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center w-6 h-6 rounded-md hover:bg-gray-700 text-gray-500 hover:text-red-400"
                title="删除对话"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteSession(session.id);
                }}
              >
                <Trash2 size={13} />
              </button>
            </div>
          );
        })}
      </div>

      {/* 底部统计 */}
      <div className="p-3 border-t border-gray-800 flex-shrink-0">
        <div className="flex items-center justify-between px-2 py-1.5 text-xs text-gray-500">
          <span>共 {sessions.length} 个对话</span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Agent 在线
          </span>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
