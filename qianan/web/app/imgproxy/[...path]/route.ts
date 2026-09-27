// 千岸生图中转：云端 SCF（腾讯云上海 → apimart/NTT 美国直连超时）经 Vercel 海外出口转发。
// 云端配置：QIANAN_IMAGE_BASE_URL=https://<vercel生产域名>/imgproxy/v1
// 客户端拼接：IMAGE_BASE_URL + "/images/generations" 与 "/tasks/{id}" 均落到本代理。
//
// ★ 挂在 /imgproxy（不在 /api 命名空间）：彻底避开 /api/:path* 的后端代理规则
// （Next 路由序中 afterFiles rewrites 先于动态段 route handler，若放 /api 会被劫持）。
// 安全：仅转发到固定上游 api.apimart.ai（非开放代理）；透传 Authorization / Content-Type / body / query。
// 注意：output:"export" 模式不支持 route handler —— 本地导出构建须先移出本目录
//（scripts/build-export.mjs 处理），Vercel 构建（VERCEL=1，output 不设 export）正常生效。
import { NextRequest, NextResponse } from "next/server";

const UPSTREAM = "https://api.apimart.ai";

async function relay(req: NextRequest, pathParts: string[]): Promise<NextResponse> {
  // [...path] 捕获 "v1/images/generations" 等；过滤空段（308 重定向可能引入尾斜杠空段）
  const rest = pathParts.filter(Boolean).join("/");
  if (!rest) {
    return NextResponse.json({ error: "missing path after /api/imgproxy" }, { status: 400 });
  }
  const target = req.url.includes("?")
    ? `${UPSTREAM}/${rest}?${req.url.split("?")[1]}`
    : `${UPSTREAM}/${rest}`;
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const auth = req.headers.get("authorization");
    if (auth) headers.Authorization = auth;
    const body =
      req.method === "GET" || req.method === "HEAD" ? undefined : await req.text();
    const r = await fetch(target, {
      method: req.method,
      headers,
      body,
      signal: AbortSignal.timeout(55_000),
    });
    const text = await r.text();
    return new NextResponse(text, {
      status: r.status,
      headers: { "Content-Type": r.headers.get("content-type") || "application/json" },
    });
  } catch (e) {
    return NextResponse.json({ error: `imgproxy relay failed: ${String(e)}` }, { status: 502 });
  }
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return relay(req, path);
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return relay(req, path);
}
