/**
 * 千岸 QianAn — 会话管理 Hook
 *
 * 纯前端内存管理 + localStorage 持久化（无后端 session API）。
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import type { Session, Message } from "../lib/chat-types";

const STORAGE_KEY = "qianan_sessions";

/** 从 localStorage 加载已保存的会话 */
function loadFromStorage(): Session[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Array<
      Omit<Session, "createdAt" | "messages"> & {
        createdAt: string;
        messages: Array<Omit<Message, "timestamp"> & { timestamp: string }>;
      }
    >;
    return parsed.map((s) => ({
      ...s,
      createdAt: new Date(s.createdAt).getTime(),
      messages: s.messages.map((m) => ({
        ...m,
        timestamp: new Date(m.timestamp).getTime(),
        // Date 对象在 JSON 中可能已丢失，恢复 isStreaming 为 false
        isStreaming: false,
      })),
    }));
  } catch {
    return [];
  }
}

/** 将会话列表写入 localStorage（防抖）*/
function saveToStorage(sessions: Session[]) {
  if (typeof window === "undefined") return;
  try {
    // 去掉 isStreaming 的流状态再保存
    const serializable = sessions.map((s) => ({
      ...s,
      messages: s.messages.map((m) => ({ ...m, isStreaming: false })),
    }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(serializable));
  } catch {
    // 忽略写入失败（可能超出配额）
  }
}

export function useSessions() {
  // Server and first client render must match. Restore browser-only history after hydration.
  const [sessions, setSessions] = useState<Session[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setSessions(loadFromStorage());
    setHydrated(true);
  }, []);

  // 防抖持久化
  useEffect(() => {
    if (!hydrated) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => saveToStorage(sessions), 500);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [hydrated, sessions]);

  const currentSession = sessions.find((s) => s.id === currentSessionId) || undefined;

  /** 创建新会话，返回 session id。可选传入标题（如首条消息）。 */
  const createSession = useCallback((title?: string): string => {
    const id = uuidv4();
    const session: Session = {
      id,
      title: title
        ? title.slice(0, 30) + (title.length > 30 ? "..." : "")
        : "新对话",
      model: "qianan-agent",
      createdAt: Date.now(),
      messages: [],
    };
    setSessions((prev) => [session, ...prev]);
    setCurrentSessionId(id);
    return id;
  }, []);

  /** 删除会话 */
  const deleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (currentSessionId === id) {
        setCurrentSessionId(null);
      }
    },
    [currentSessionId],
  );

  /** 选择会话 */
  const selectSession = useCallback((id: string) => {
    setCurrentSessionId(id);
  }, []);

  /** 更新会话的消息列表（函数式更新） */
  const updateMessages = useCallback(
    (sessionId: string, updater: (messages: Message[]) => Message[]) => {
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== sessionId) return s;
          const newMessages = updater(s.messages);
          // 如果是第一条消息，用消息内容更新标题
          const newTitle =
            s.messages.length === 0 && newMessages.length > 0 && newMessages[0]?.content
              ? newMessages[0].content.slice(0, 30) +
                (newMessages[0].content.length > 30 ? "..." : "")
              : s.title;
          return { ...s, messages: newMessages, title: newTitle };
        }),
      );
    },
    [],
  );

  return {
    sessions,
    setSessions,
    currentSessionId,
    currentSession,
    createSession,
    deleteSession,
    selectSession,
    updateMessages,
  };
}
