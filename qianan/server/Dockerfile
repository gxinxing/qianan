# 注意：不使用 `# syntax=docker/dockerfile:1` 指令 —— 本机 Docker 配置的 registry mirror
# 拉取该 frontend 镜像会 403，且本文件用到的指令（多阶段/ARG/COPY --from/--chown）
# 内置 frontend 全部支持，去掉该行可消除一次不必要的网络依赖（演示机已实测会失败）。
#
# 多阶段构建：
#   Stage 1 (builder)  —— 编译/下载依赖 wheel，gcc 等编译工具留在这一层，不进最终镜像
#   Stage 2 (runtime) —— 最终镜像，非 root 运行
#
# 为什么不用 mcr.microsoft.com/playwright/python 官方镜像？
#   1) 官方镜像基于 Ubuntu（含 chromium/firefox/webkit 三家浏览器，约 2GB+），
#      我们只依赖 chromium，按需安装体积小得多；
#   2) 官方镜像的 Python/glibc 与 python:3.10-slim 不一致，builder 阶段产出的
#      wheel 无法直接复用。两段同为 python:3.10-slim，wheel 精确可移植；
#   3) 保持与原 Dockerfile 相同的基础镜像/Python 版本语义。
# 浏览器安装层在最重的位置单独成层：只要本文件不改，依赖再怎么变也不重复下载。

###############################################################################
# Stage 1/2 · deps-builder
###############################################################################
FROM python:3.10-slim AS builder

WORKDIR /build

# 编译工具只存在于 builder 阶段（旧版把它装进了最终镜像，白增 ~150MB）
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 先拷 requirements.txt：依赖不变时该层长期命中缓存
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

###############################################################################
# Stage 2/2 · runtime（最终镜像，非 root 运行）
###############################################################################
FROM python:3.10-slim AS runtime

# curl：docker-compose healthcheck（curl -f http://localhost:8000/api/health）依赖，
# 原基础镜像不含 curl，必须显式安装
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 非 root 运行用户；uid 可在构建时对齐宿主（--build-arg APP_UID=1000）
ARG APP_UID=10001
RUN useradd --create-home --uid "${APP_UID}" qianan \
    && mkdir -p /app \
    && chown qianan:qianan /app

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Playwright + Chromium：publisher 上架链路（演示主路径）依赖。
# --with-deps 补齐 slim 镜像缺失的 chromium 运行库（旧版漏装，容器内必崩）；
# fonts-noto-cjk：mock 卖家页为中文 UI，无 CJK 字体时 publisher 截图会变豆腐块。
# 国内构建慢可换浏览器下载源：
#   docker build --build-arg PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
ARG PLAYWRIGHT_DOWNLOAD_HOST=
RUN if [ -n "$PLAYWRIGHT_DOWNLOAD_HOST" ]; then export PLAYWRIGHT_DOWNLOAD_HOST; fi \
    && pip install --no-cache-dir playwright \
    && playwright install --with-deps chromium \
    && apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 业务依赖：从 builder 的 wheel 离线安装（只在 requirements.txt 变化时重建此层）
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# 应用代码（受 .dockerignore 约束：密钥 / 部署产物 / 运行时数据不进镜像）
COPY --chown=qianan:qianan . .

EXPOSE 8000

USER qianan

# 启动命令（与原 Dockerfile 语义一致）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
