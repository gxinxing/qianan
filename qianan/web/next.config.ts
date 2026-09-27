import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 仓库外存在一个游离的 package-lock.json（/Users/simon/package-lock.json），
  // Next.js 会误把它当 workspace root 并告警；显式锁定到本项目目录（web/）。
  outputFileTracingRoot: __dirname,

  // CloudBase 静态托管：静态导出 out/；Vercel 构建时关掉导出模式（保留 route handlers，
  // 如 app/api/imgproxy 生图中转）——两种构建产物各自适配宿主。
  // 注意：export 模式不支持 route handler，本地导出构建须先移出 app/api（scripts/build-export.mjs）。
  output: process.env.VERCEL ? undefined : "export",

  // 导出为 login/index.html 形态（而非 login.html）：静态服务器能直接打开深链 /
  // 刷新子页面，不再依赖「404 回落 index.html」的托管配置。
  // Vercel 构建时关闭：route handler 路径（/api/imgproxy/...）避免每次请求多一跳 308。
  trailingSlash: process.env.VERCEL ? false : true,

  // /api 代理（前端 → cloudbase 后端）：afterFiles —— 未命中 filesystem（页面/route handler）的
  // /api/* 才转发后端。生图中转挂在 /imgproxy（见 app/imgproxy），不在此命名空间内，
  // 彻底避开本条规则（Next 路由序中动态段 route handler 排在 afterFiles 之后，放 /api 会被劫持）。
  async rewrites() {
    return {
      beforeFiles: [],
      afterFiles: [
        {
          source: "/api/:path*",
          destination: "https://ai-native-d5gfb0dm2a28d1fe9-1419921079.ap-shanghai.app.tcloudbase.com/api/:path*",
        },
      ],
      fallback: [],
    };
  },

  // 图片用原生 <img> 加载（已允许外部图床），无需图片优化服务
  images: {
    unoptimized: true,
    remotePatterns: [{ protocol: "https", hostname: "**" }],
  },

  // 静态导出忽略 TS/ESLint 构建错误（hackathon 速度优先）
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
