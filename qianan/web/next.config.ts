import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker 部署：standalone 产物（server.js + 最小 node_modules），
  // 由根 docker-compose.yml 的 frontend 服务运行（见 qianan/web/Dockerfile）
  output: "standalone",

  // 图片用原生 <img> 加载（已允许外部图床），无需图片优化服务
  images: {
    unoptimized: true,
    remotePatterns: [{ protocol: "https", hostname: "**" }],
  },
};

export default nextConfig;
