#!/bin/bash
# 千岸 QianAn — 腾讯云 CloudBase 一键部署脚本
# 使用前请先配置凭据：export TENCENT_SECRET_ID=xxx TENCENT_SECRET_KEY=xxx
set -e

echo "=========================================="
echo "  千岸 QianAn — CloudBase 部署"
echo "=========================================="

# 检查凭据
if [ -z "$TENCENT_SECRET_ID" ] || [ -z "$TENCENT_SECRET_KEY" ]; then
    echo "⚠️ 请先设置环境变量："
    echo "  export TENCENT_SECRET_ID=你的SecretID"
    echo "  export TENCENT_SECRET_KEY=你的SecretKey"
    echo ""
    echo "或者直接运行登录："
    echo "  cloudbase login -k"
    exit 1
fi

PROJECT_DIR="/Users/simon/Documents/01_AI and Code Development/AI+跨境黑客松巅峰赛"
CLOUDBASE_DIR="$PROJECT_DIR/cloudbase"

# 登录
echo "🔑 登录腾讯云..."
cloudbase login --apiKeyId "$TENCENT_SECRET_ID" --apiKey "$TENCENT_SECRET_KEY"

# 初始化/选择 CloudBase 环境
echo "📦 初始化 CloudBase 项目..."
cd "$CLOUDBASE_DIR"
cloudbase init --select-existing-env 2>/dev/null || cloudbase init

# 部署云函数
echo "🚀 部署云函数 qianan-api..."
cloudbase functions:deploy qianan-api --source ../qianan/server/deploy_pkg --runtime Python3.10 --timeout 120

# 部署前端静态托管
echo "🌐 部署前端静态托管..."
cd "$PROJECT_DIR/qianan/web"
npm run build
cloudbase hosting:deploy

echo ""
echo "=========================================="
echo "  ✅ 部署完成！"
echo "=========================================="
echo "前端 URL: $(cloudbase hosting:url 2>/dev/null || echo '检查 CloudBase 控制台')"
echo "云函数 URL: 检查 CloudBase 控制台 → 云函数 → qianan-api → 触发路径"
