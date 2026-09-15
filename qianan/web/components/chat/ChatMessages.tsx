"use client";

/**
 * 千岸 QianAn — 对话消息列表
 *
 * 暗色主题，按 ContentBlock 顺序渲染 text + tool_use 交替内容。
 */

import { useRef, useEffect } from "react";
import { User, Bot, Loader2 } from "lucide-react";
import type { Message, ContentBlock } from "../../lib/chat-types";
import { ToolCallsCollapse } from "./ToolCallsCollapse";

interface ChatMessagesProps {
  messages: Message[];
}

export function ChatMessages({ messages }: ChatMessagesProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 新消息时自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* ---- 渲染单个内容块 ---- */
  const renderBlock = (
    block: ContentBlock,
    index: number,
    isStreaming?: boolean,
    isLast?: boolean,
  ) => {
    if (block.type === "text") {
      return (
        <div
          key={`text-${index}`}
          className="px-4 py-3 leading-relaxed break-words bg-gray-800 text-gray-100 rounded-2xl rounded-bl-md"
        >
          <div className="whitespace-pre-wrap">{block.text}</div>
          {isStreaming && isLast && (
            <span className="inline-block w-2 h-4 ml-0.5 bg-cyan-400 animate-pulse align-middle" />
          )}
        </div>
      );
    }

    if (block.type === "tool_use") {
      return (
        <ToolCallsCollapse
          key={`tool-${block.toolCall.id}`}
          toolCalls={[block.toolCall]}
          isStreaming={isStreaming && block.toolCall.status === "running"}
        />
      );
    }

    return null;
  };

  /* ---- 渲染 assistant 内容 ---- */
  const renderAssistantContent = (message: Message) => {
    if (message.contentBlocks && message.contentBlocks.length > 0) {
      return message.contentBlocks.map((block, index) =>
        renderBlock(
          block,
          index,
          message.isStreaming,
          index === message.contentBlocks!.length - 1,
        ),
      );
    }

    // 兼容旧数据
    return (
      <>
        {message.toolCalls && message.toolCalls.length > 0 && (
          <ToolCallsCollapse toolCalls={message.toolCalls} isStreaming={message.isStreaming} />
        )}
        {message.content && (
          <div className="px-4 py-3 leading-relaxed break-words bg-gray-800 text-gray-100 rounded-2xl rounded-bl-md">
            <div className="whitespace-pre-wrap">{message.content}</div>
            {message.isStreaming && (
              <span className="inline-block w-2 h-4 ml-0.5 bg-cyan-400 animate-pulse align-middle" />
            )}
          </div>
        )}
      </>
    );
  };

  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500 gap-3">
        <Bot size={48} className="opacity-30" />
        <p className="text-sm text-center max-w-xs">发一稿商品，千岸会在这次会话里完成一次跨平台上新：<br />理解 → 文案 → 审核 → 出图 → 交付。<br /><span className="text-gray-600">一个会话 = 一次上新任务</span></p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 max-w-3xl mx-auto w-full">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex gap-3 ${message.role === "user" ? "flex-row-reverse" : ""}`}
        >
          {/* 头像 */}
          <div
            className={`w-9 h-9 flex items-center justify-center flex-shrink-0 rounded-full self-start ${
              message.role === "user"
                ? "bg-cyan-600 text-white"
                : "bg-gray-700 text-gray-200"
            }`}
          >
            {message.role === "user" ? <User size={18} /> : <Bot size={18} />}
          </div>

          {/* 消息体 */}
          <div
            className={`flex flex-col gap-2 max-w-[80%] ${
              message.role === "user" ? "items-end" : ""
            }`}
          >
            {/* 用户消息 */}
            {message.role === "user" && (
              <div className="px-4 py-3 leading-relaxed break-words bg-cyan-600 text-white rounded-2xl rounded-br-md">
                {message.content}
              </div>
            )}

            {/* Agent 消息 */}
            {message.role === "assistant" && renderAssistantContent(message)}

            {/* 思考中状态 */}
            {message.role === "assistant" &&
              message.isStreaming &&
              !message.content &&
              (!message.contentBlocks || message.contentBlocks.length === 0) &&
              (!message.toolCalls || message.toolCalls.length === 0) && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800">
                  <Loader2 size={14} className="animate-spin text-gray-400" />
                  <span className="text-sm text-gray-400">思考中...</span>
                </div>
              )}
          </div>
        </div>
      ))}

      <div ref={messagesEndRef} />
    </div>
  );
}

export default ChatMessages;
