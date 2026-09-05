# syntax=docker/dockerfile:1

########################################################################
# 阶段 1 · deps —— 按锁文件安装依赖（利用 docker 层缓存）
########################################################################
FROM node:20-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

########################################################################
# 阶段 2 · build —— next build（output:"standalone" 产出 .next/standalone）
########################################################################
FROM node:20-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* 在构建期内联进客户端产物；默认与 docker-compose 的 backend 端口对齐。
# 如部署地址不同，可在 compose 的 build.args 里覆盖 NEXT_PUBLIC_API_URL。
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

########################################################################
# 阶段 3 · runner —— 最小运行时（standalone server.js + 静态资源）
########################################################################
FROM node:20-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN groupadd --system --gid 1001 nodejs \
 && useradd --system --uid 1001 --gid nodejs nextjs
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
