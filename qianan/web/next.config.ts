import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 仓库外存在一个游离的 package-lock.json（/Users/simon/package-lock.json），
  // Next.js 会误把它当 workspace root 并告警；显式锁定到本项目目录（web/）。
  outputFileTracingRoot: __dirname,

  // CloudBase 静态托管：静态导出 out/
  output: "export",

  // 导出为 login/index.html 形态（而非 login.html）：静态服务器能直接打开深链 /
  // 刷新子页面，不再依赖「404 回落 index.html」的托管配置。
  trailingSlash: true,

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
