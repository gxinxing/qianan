import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // CloudBase 静态托管：静态导出 out/
  output: "export",

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
