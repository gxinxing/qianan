"use client";

/**
 * 自包含认证客户端（替代 CloudBase Web SDK）。
 *
 * - 对接后端 /api/auth/{register,login}，token 存 localStorage，供 api.ts 在每次请求里带上 Bearer。
 * - 保留与旧 CloudBase 封装一致的导出名（getAccessToken / setAccessToken / initAuth /
 *   signInWithPassword / signUpWithPassword / signOut / refreshToken / authRef / appRef），
 *   因此 AuthProvider 与 api.ts 无需改动。
 * - 后端以 HS256 JWT 签发令牌，按 uid 做服务端强制租户隔离（详见 server/app/auth.py）。
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8001";

const TOKEN_KEY = "qa_cb_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(t: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (t) window.localStorage.setItem(TOKEN_KEY, t);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

async function postJSON(path: string, body: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    /* ignore */
  }
  if (!res.ok) {
    const msg = (data && (data.detail || data.error)) || "请求失败";
    throw typeof msg === "string" ? new Error(msg) : msg;
  }
  return data;
}

async function _authenticate(
  username: string,
  password: string,
  path: string,
): Promise<any> {
  const data = await postJSON(path, { username, password });
  setAccessToken(data?.token || null);
  return data;
}

export async function signInWithPassword(username: string, password: string) {
  return _authenticate(username, password, "/api/auth/login");
}

export async function signUpWithPassword(username: string, password: string) {
  return _authenticate(username, password, "/api/auth/register");
}

export async function signOut() {
  setAccessToken(null);
}

export async function refreshToken() {
  // 后端 JWT 长期有效；此处仅确认本地存在令牌即可。
  return getAccessToken();
}

export function initAuth(): Promise<any> {
  return Promise.resolve(null);
}

export function authRef(): any {
  return null;
}

export function appRef(): any {
  return null;
}
