"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { API_BASE } from "@/lib/api";
import {
  authRef,
  getAccessToken,
  initAuth,
  refreshToken,
  setAccessToken,
  signInWithPassword,
  signOut as cbSignOut,
  signUpWithPassword,
} from "@/lib/cloudbase";

export interface AuthUser {
  uid: string;
  username: string;
  name: string;
  authenticated: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  ready: boolean;
  /**
   * 后端是否强制登录（/api/health 的 auth.require_auth）。
   * false = 演示模式允许游客直连，前端不应把用户拦在登录墙外；
   * null = 尚未探测到（此时按需要登录处理，避免闪现无权限内容）。
   */
  requireAuth: boolean | null;
  signIn: (username: string, password: string) => Promise<void>;
  signUp: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function toUser(session: any): AuthUser | null {
  if (!session) return null;
  // 自包含鉴权：后端 /api/auth/{login,register} 直接返回 { token, uid, username, name? }
  if (session.uid || session.username) {
    return {
      uid: session.uid || "",
      username: session.username || "",
      name: session.name || session.username || "",
      authenticated: true,
    };
  }
  // 兼容 CloudBase 会话结构 { session: { user } }
  const s = session?.session;
  if (!s || !s.user) return null;
  const u = s.user;
  return {
    uid: u.id || u.uid || u.sub || "",
    username: u.username || u.email || u.phone || "",
    name: u.name || u.username || "",
    authenticated: true,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const [requireAuth, setRequireAuth] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      await initAuth();
      // 探测后端是否强制登录：false 时前端不拦游客（演示模式），保持与后端一致
      try {
        const hres = await fetch(`${API_BASE}/api/health`);
        if (hres.ok) {
          const health = await hres.json();
          if (alive) setRequireAuth(health?.auth?.require_auth === true);
        }
      } catch {
        /* 探测失败：按需要登录处理 */
      }
      // 自包含鉴权：若本地已存 token，向 /api/me 还原登录态（兼容页面刷新）
      const token = getAccessToken();
      if (token) {
        try {
          const res = await fetch(`${API_BASE}/api/me`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.ok) {
            const me = await res.json();
            if (alive && me) {
              setUser({
                uid: me.uid,
                username: me.username,
                name: me.name || me.username,
                authenticated: true,
              });
            }
          } else if (res.status === 401) {
            setAccessToken(null);
          }
        } catch {
          /* 网络异常：保持未登录 */
        }
      }
      if (alive) {
        setReady(true);
        setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const data = await signInWithPassword(username, password);
    setUser(toUser(data));
  }, []);

  const signUp = useCallback(async (username: string, password: string) => {
    await signUpWithPassword(username, password);
    // 注册成功后 CloudBase 通常会自动建立会话；尝试登录兜底
    try {
      const data = await signInWithPassword(username, password);
      setUser(toUser(data));
    } catch {
      /* 若需邮件/短信确认，则等待 */
    }
  }, []);

  const signOut = useCallback(async () => {
    await cbSignOut();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, ready, requireAuth, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 <AuthProvider> 内使用");
  return ctx;
}
