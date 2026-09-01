import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 生产环境输出独立部署包（FC / Vercel / Docker）
  output: "standalone",

  // 开发环境本地代理：前端 3000 → 后端 8000，避免 CORS
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },

  // 图片优化：允许外部图床（百炼返回的图片 URL）
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },

  // 构建时静态导出排除（所有页面都是 dynamic，不需要排除）
};

export default nextConfig;
