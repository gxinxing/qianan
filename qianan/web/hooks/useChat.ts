/**
 * 千岸 QianAn — 对话 Hook
 *
 * 适配后端 POST /api/chat 的 SSE 协议（init / trace / listing / done）。
 * 参考 MovieWeaver useChat.ts 的 ReadableStream 解析模式。
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { v4 as uuidv4 } from "uuid";
import type { Message, ContentBlock, ToolCall, ListingSnapshot, ListingItem } from "../lib/chat-types";
import { useSessions } from "./useSessions";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export interface UseChatOptions {
  /** 额外请求体字段，由调用方从产品表单收集 */
  getExtraPayload?: () => Record<string, unknown>;
  /** listing 事件回调（驱动右侧产物面板） */
  onListingEvent?: (snapshot: ListingSnapshot) => void;
}

export function useChat(options: UseChatOptions = {}) {
  const { getExtraPayload, onListingEvent } = options;
  const sessions = useSessions();
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  /** 当前流式任务的后端 id，用于「停止」时通知后端真正中断 Agent */
  const taskIdRef = useRef<string | null>(null);
  /** 最近一次产物快照（listing_full 或合并后的 listing_update），用于把单平台更新合并进去 */
  const snapshotRef = useRef<ListingSnapshot | null>(null);

  // 保持 onListingEvent 最新
  const onListingRef = useRef(onListingEvent);
  useEffect(() => {
    onListingRef.current = onListingEvent;
  }, [onListingEvent]);

  /**
   * 发送一条用户消息并流式接收 Agent 回复。
   */
  const sendMessage = useCallback(
    async (text: string, images?: string[]) => {
      const messageContent = text.trim();
      const hasImages = images && images.length > 0;
      if ((!messageContent && !hasImages) || isLoading) return;

      // ---- 1. 确保有 session（首条消息时自动创建）----
      let sessionId = sessions.currentSessionId;
      if (!sessionId) {
        sessionId = sessions.createSession(messageContent);
      }

      const userMessageId = uuidv4();
      const assistantMessageId = uuidv4();

      const userMessage: Message = {
        id: userMessageId,
        role: "user",
        content: messageContent,
        timestamp: Date.now(),
      };

      const assistantMessage: Message = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        timestamp: Date.now(),
        isStreaming: true,
        contentBlocks: [],
        toolCalls: [],
      };

      sessions.updateMessages(sessionId, (prev) => [...prev, userMessage, assistantMessage]);
      setIsLoading(true);
      // 新任务开始：清空上一轮合并快照，避免跨任务的平台产物串台
      snapshotRef.current = null;

      // ---- 2. 发起 SSE 请求 ----
      const controller = new AbortController();
      abortRef.current = controller;

      const extra = getExtraPayload?.() || {};

      try {
        const response = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: messageContent,
            ...extra,
            ...(hasImages ? { image_base64: images![0] } : {}),
          }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`API ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        // SSE 解析状态
        let buffer = "";
        const contentBlocks: ContentBlock[] = [];
        const toolCalls: ToolCall[] = [];
        let currentText = "";

        /** 将更新写回当前 assistant 消息 */
        const flush = () => {
          sessions.updateMessages(sessionId!, (prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? {
                    ...m,
                    content: currentText,
                    contentBlocks: [...contentBlocks],
                    toolCalls: [...toolCalls],
                  }
                : m,
            ),
          );
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // 按 \n 分割，处理完整行
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // 最后一段不完整，留到下次

          for (const raw of lines) {
            const line = raw.trim();
            if (!line.startsWith("data:")) continue;

            const payload = line.slice(5).trim();
            if (!payload) continue;

            try {
              const data = JSON.parse(payload);

              if (data.type === "init") {
                taskIdRef.current = data.task_id || null;
                continue;
              }

              if (data.type === "text") {
                // Agent 的文本回复（"我在做X"）
                contentBlocks.push({ type: "text", text: data.content });
                currentText = "";
                flush();
                continue;
              }

              if (data.type === "trace") {
                // 工具调用追踪
                if (currentText) {
                  contentBlocks.push({ type: "text", text: currentText });
                  currentText = "";
                }

                const toolId = uuidv4();
                const isError = data.status === "error" || data.status === "fallback";
                const tc: ToolCall = {
                  id: toolId,
                  name: data.tool || "unknown",
                  input: data.args || data.args_summary || "",
                  status: isError ? "error" : "completed",
                  result: data.result || data.result_summary || undefined,
                  isError,
                };
                toolCalls.push(tc);
                contentBlocks.push({ type: "tool_use", toolCall: tc });
                flush();
                continue;
              }

              // 单平台实时产物更新：后端事件类型为 listing_update（旧协议 listing 兼容）。
              // 必须合并进已有快照，否则整块替换会把其他平台产物冲掉（P0 #2：右侧面板丢状态）。
              if (data.type === "listing" || data.type === "listing_update") {
                const item: ListingItem = {
                  platform: data.platform,
                  display_name: data.display_name,
                  title: data.title,
                  bullets: data.bullets || [],
                  description: data.description || "",
                  images: data.images || [],
                  detail_images: data.detail_images || [],
                  video_url: data.video_url || null,
                  compliance_passed: data.compliance_passed ?? true,
                  revised_count: data.revised_count || 0,
                  compliance_errors: data.compliance_errors || 0,
                  compliance_warns: data.compliance_warns || 0,
                };
                const prev = snapshotRef.current;
                const listings = (prev?.listings ?? []).filter(
                  (l) => l.platform !== data.platform,
                );
                listings.push(item);
                const merged: ListingSnapshot = {
                  status: prev?.status ?? "running",
                  stage: prev?.stage ?? (data.display_name || data.platform || ""),
                  progress: prev?.progress ?? 0.5,
                  plan: prev?.plan ?? null,
                  memory_recall: prev?.memory_recall ?? [],
                  reflections: prev?.reflections ?? [],
                  listings,
                };
                snapshotRef.current = merged;
                onListingRef.current?.(merged);
                continue;
              }

              if (data.type === "listing_full") {
                // 全量快照（权威）：直接替换，含 status/stage/progress/plan/memory/reflections
                const snapshot: ListingSnapshot = {
                  status: data.status,
                  stage: data.stage,
                  progress: data.progress,
                  plan: data.plan ?? null,
                  memory_recall: data.memory_recall || data.memoryRecall || [],
                  reflections: data.reflections || [],
                  listings: data.listings || [],
                };
                snapshotRef.current = snapshot;
                onListingRef.current?.(snapshot);
                continue;
              }

              if (data.type === "done") {
                // 完成事件
                if (currentText) {
                  contentBlocks.push({ type: "text", text: currentText });
                  currentText = "";
                }
                sessions.updateMessages(sessionId!, (prev) =>
                  prev.map((m) =>
                    m.id === assistantMessageId
                      ? { ...m, isStreaming: false, contentBlocks: [...contentBlocks] }
                      : m,
                  ),
                );
                continue;
              }
            } catch {
              // JSON 解析失败 — 忽略
            }
          }
        }

        // 流结束 — 确保 isStreaming 关闭
        sessions.updateMessages(sessionId!, (prev) =>
          prev.map((m) =>
            m.id === assistantMessageId ? { ...m, isStreaming: false } : m,
          ),
        );
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // 用户主动取消
        } else {
          console.error("Chat error:", err);
          sessions.updateMessages(sessionId!, (prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? { ...m, content: "发生错误，请重试", isStreaming: false }
                : m,
            ),
          );
        }
      } finally {
        setIsLoading(false);
        abortRef.current = null;
      }
    },
    [isLoading, sessions, getExtraPayload],
  );

  /** 中止当前流式请求，并通知后端真正停止后台 Agent */
  const handleStop = useCallback(() => {
    // ① 断开 SSE —— 只是不再接收事件，后台仍会继续跑
    abortRef.current?.abort();
    setIsLoading(false);

    // ② 通知后端停止 —— 否则模型额度会一直烧到本轮工具结束
    const taskId = taskIdRef.current;
    if (taskId) {
      fetch(`${API_BASE}/api/chat/${taskId}/cancel`, { method: "POST" }).catch(() => {
        // 取消是尽力而为：后端已结束或网络断开都不影响前端状态
      });
      taskIdRef.current = null;
    }
  }, []);

  return {
    // session 管理（透传）
    sessions: sessions.sessions,
    currentSessionId: sessions.currentSessionId,
    currentSession: sessions.currentSession,
    createSession: sessions.createSession,
    deleteSession: sessions.deleteSession,
    selectSession: sessions.selectSession,
    // chat
    isLoading,
    sendMessage,
    handleStop,
  };
}
