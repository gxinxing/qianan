"use client";

/**
 * 千岸 QianAn Studio — 对话式 Agent 页面
 *
 * 三栏布局：Sidebar | ChatArea | ListingPanel
 * 参考 MovieWeaver Studio 的 chat-driven agent 体验。
 */

import { useState, useCallback } from "react";
import { useChat } from "../../hooks/useChat";
import { Sidebar } from "../../components/chat/Sidebar";
import { ChatMessages } from "../../components/chat/ChatMessages";
import { ChatInput } from "../../components/chat/ChatInput";
import { ListingPanel } from "../../components/chat/ListingPanel";
import type { ListingSnapshot } from "../../lib/chat-types";

export default function StudioPage() {
  const [inputValue, setInputValue] = useState("");
  const [listingSnapshot, setListingSnapshot] = useState<ListingSnapshot | null>(null);

  const chat = useChat({
    onListingEvent: useCallback((snapshot: ListingSnapshot) => {
      setListingSnapshot(snapshot);
    }, []),
  });

  const handleSend = useCallback(
    (message: string, images?: string[]) => {
      setInputValue("");
      setListingSnapshot(null); // 重置产物面板
      chat.sendMessage(message, images);
    },
    [chat],
  );

  const handleNewChat = useCallback(() => {
    chat.createSession();
    setListingSnapshot(null);
  }, [chat]);

  return (
    <div className="flex h-screen overflow-hidden bg-gray-900 text-gray-100">
      {/* 左栏：侧边栏 */}
      <Sidebar
        sessions={chat.sessions}
        currentSessionId={chat.currentSessionId}
        onNewChat={handleNewChat}
        onSelectSession={chat.selectSession}
        onDeleteSession={chat.deleteSession}
      />

      {/* 中栏：对话区 */}
      <main className="flex flex-col flex-1 min-w-0">
        {/* 顶部标题栏 */}
        <header className="h-14 px-6 flex items-center justify-between border-b border-gray-800 flex-shrink-0">
          <div className="flex items-center gap-2">
            <h1 className="text-sm font-semibold text-gray-200">千岸 Agent Studio</h1>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-400">
              v1.0
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              {chat.isLoading ? "生成中..." : "空闲"}
            </span>
          </div>
        </header>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <ChatMessages messages={chat.currentSession?.messages || []} />
        </div>

        {/* 输入框 */}
        <ChatInput
          inputValue={inputValue}
          isLoading={chat.isLoading}
          onChange={setInputValue}
          onSend={handleSend}
          onStop={chat.handleStop}
        />
      </main>

      {/* 右栏：产物面板 */}
      <ListingPanel snapshot={listingSnapshot} />
    </div>
  );
}
