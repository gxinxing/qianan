"use client";

import { useEffect, useRef } from "react";
import { Bot, Check, Loader2, TriangleAlert, Wrench } from "lucide-react";
import type { Message, ToolCall } from "../../lib/chat-types";

interface ChatMessagesProps { messages: Message[] }

function ToolStep({ tool }: { tool: ToolCall }) {
  const failed = tool.status === "error" || tool.isError;
  const running = tool.status === "running";
  return (
    <details className="chat-tool-step">
      <summary>
        {running ? <Loader2 size={13} className="animate-spin" /> : failed ? <TriangleAlert size={13} /> : <Check size={13} />}
        <span>{tool.name.replaceAll("_", " ")}</span>
        <small>{running ? "执行中" : failed ? "需要关注" : "已完成"}</small>
      </summary>
      {(tool.input || tool.result) && (
        <div className="chat-tool-detail">
          {tool.input && <p>{typeof tool.input === "string" ? tool.input : JSON.stringify(tool.input)}</p>}
          {tool.result && <p>{tool.result}</p>}
        </div>
      )}
    </details>
  );
}

export function ChatMessages({ messages }: ChatMessagesProps) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);

  return (
    <div className="chat-thread" aria-live="polite">
      {messages.map((message) => (
        <article key={message.id} className={`chat-message is-${message.role}`}>
          {message.role === "assistant" && <div className="chat-avatar" aria-hidden="true"><Bot size={16} /></div>}
          <div className="chat-message-body">
            {message.role === "user" ? (
              <div className="chat-user-bubble">{message.content || "已上传商品图片"}</div>
            ) : (
              <>
                {message.contentBlocks?.map((block, index) => block.type === "text" ? (
                  <p className="chat-agent-copy" key={`text-${index}`}>{block.text}</p>
                ) : <ToolStep key={block.toolCall.id} tool={block.toolCall} />)}
                {!message.contentBlocks?.length && message.toolCalls?.map((tool) => <ToolStep key={tool.id} tool={tool} />)}
                {message.content && !message.contentBlocks?.length && <p className="chat-agent-copy">{message.content}</p>}
                {message.isStreaming && !message.content && !message.contentBlocks?.length && (
                  <div className="chat-thinking"><Wrench size={14} /><span>正在理解商品并规划任务</span><i /><i /><i /></div>
                )}
              </>
            )}
          </div>
        </article>
      ))}
      <div ref={endRef} />
    </div>
  );
}

export default ChatMessages;
