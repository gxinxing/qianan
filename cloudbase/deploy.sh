#!/bin/bash
# 千岸 QianAn — 腾讯云 CloudBase 一键部署（tcb CLI 3.8.1，2026-09-07 全链路实测）
#
# 前置：
#   npm i -g @cloudbase/cli && tcb login     # 凭据在 ~/.config/.cloudbase
#   qianan/server/.env 需含 BAILIAN_API_KEY、QIANAN_DASHSCOPE_API_KEY 与 QIANAN_JWT_SECRET
#   （密钥仅经临时物化配置注入云端环境变量，本脚本与 cloudbaserc.json 均不含明文密钥）
#
# 用法：
#   ./deploy.sh              全量：后端云函数 + 前端静态托管
#   ./deploy.sh --api-only   只更新后端（云函数代码 + 环境变量），不动前端
#                            —— 换 AI 网关密钥/后后端改动时用，避免重跑 npm build
#
# 云端 URL（访问路径 /api/** → qianan-api 为控制台一次性配置，重建函数后自动随名复挂）：
#   前端:  https://<env>-<uin>.tcloudbaseapp.com
#   API:   https://<env>-<uin>.ap-shanghai.app.tcloudbase.com/api/**
#
# 已趟平的坑（实测记录见 docs/05-集成验证报告.md）：
#   1. deploy_pkg 的 vendored 依赖必须是 linux cp310 wheel——macOS 版 .so 会让云端
#      init 秒崩，网关一律 443（本脚本内置校验与修复指引）
#   2. scf_bootstrap 必须用绝对路径解释器 /var/lang/python310/bin/python3.10（裸 python3 不可用）
#   3. 前端构建必须清 .next 缓存——陈旧 webpack 缓存会残留旧 API base（localhost:8001）
#   4. .env.local 在生产构建同样生效、遮蔽 .env.production —— 本地覆盖请用 .env.development
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$PROJECT_DIR/qianan/server"
PKG_DIR="$SERVER_DIR/deploy_pkg"
WEB_DIR="$PROJECT_DIR/qianan/web"
ENV_ID="ai-native-d5gfb0dm2a28d1fe9"
UIN="1419921079"
API_URL="https://$ENV_ID-$UIN.ap-shanghai.app.tcloudbase.com"
FRONT_URL="https://$ENV_ID-$UIN.tcloudbaseapp.com"
SERVER_ENV="$SERVER_DIR/.env"
TMP_RC="$(mktemp /tmp/qianan-cloudbaserc.XXXXXX.json)"
trap 'rm -f "$TMP_RC"' EXIT

export PATH="$HOME/.npm-global/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

command -v tcb >/dev/null || { echo "❌ 未安装 @cloudbase/cli：npm i -g @cloudbase/cli"; exit 1; }
command -v expect >/dev/null || { echo "❌ 缺少 expect（macOS 自带 /usr/bin/expect）"; exit 1; }
[ -f "$SERVER_ENV" ] || { echo "❌ 缺少 $SERVER_ENV"; exit 1; }

# --api-only：跳过第 5 步前端构建与托管部署。前端未改、只换后端网关密钥时用，
# 避免重跑 npm build 覆盖已上线的前端产物。
API_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --api-only) API_ONLY=1 ;;
    *) echo "❌ 未知参数：$arg（可用：--api-only）"; exit 1 ;;
  esac
done

for k in BAILIAN_API_KEY QIANAN_DASHSCOPE_API_KEY QIANAN_JWT_SECRET; do
  grep -q "^$k=" "$SERVER_ENV" || { echo "❌ $SERVER_ENV 缺少 $k"; exit 1; }
done

echo "📦 1/6 同步部署包 app/data/rules ..."
rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' "$SERVER_DIR/app/" "$PKG_DIR/app/"
# data 为运行态目录：仅打包只读种子资源，任务/发布产物不入包（曾致 145MB 巨包 init 超时）
rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='tasks/' --exclude='publish/' --exclude='metrics/' \
  --exclude='mock_seller/' --exclude='owners.json' \
  "$SERVER_DIR/data/" "$PKG_DIR/data/"
rsync -a --delete "$SERVER_DIR/rules/" "$PKG_DIR/rules/"

echo "🐍 2/6 校验 SCF 入口与 linux cp310 依赖 ..."
cp "$SERVER_DIR/scf/scf_bootstrap" "$SERVER_DIR/scf/scf_serve.py" "$PKG_DIR/"
chmod 755 "$PKG_DIR/scf_bootstrap"
if ! ls "$PKG_DIR"/pydantic_core/_pydantic_core.cpython-310-*linux-gnu.so >/dev/null 2>&1; then
  echo "❌ deploy_pkg 缺少 linux cp310 编译依赖（现在只有 macOS 版或缺失，云端必然 init 崩溃）。"
  echo "   修复命令："
  echo "   qianan/server/.venv/bin/python3 -m pip install \\"
  echo "     --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 \\"
  echo "     --implementation cp --abi cp310 --python-version 3.10 --only-binary=:all: \\"
  echo "     --no-compile --target $PKG_DIR -r $SERVER_DIR/scf/requirements-linux-cp310.txt"
  exit 1
fi

echo "🔑 3/6 物化含密钥的临时配置（用后即焚）..."
python3 - "$SCRIPT_DIR/cloudbaserc.json" "$TMP_RC" "$SERVER_ENV" <<'PY'
import json, sys
src, dst, env_path = sys.argv[1], sys.argv[2], sys.argv[3]
env = {}
for line in open(env_path):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
cfg = json.load(open(src))
ev = cfg["functions"][0]["envVariables"]
# 密钥不落仓：部署时从 .env 物化进临时配置，脚本本身与 cloudbaserc.json 只有 ${env.X} 占位符
for k in ("BAILIAN_API_KEY", "QIANAN_DASHSCOPE_API_KEY", "QIANAN_JWT_SECRET"):
    ev[k] = env[k]
json.dump(cfg, open(dst, "w"), ensure_ascii=False, indent=2)
PY

# 云函数不存在时先以 HTTP 型创建（类型创建后不可更改）
if ! tcb fn list --json 2>/dev/null | grep -q '"name": "qianan-api"'; then
  echo "🆕 云函数不存在，以 HTTP 型创建 ..."
  (cd "$SCRIPT_DIR" && tcb fn deploy qianan-api --httpFn --config-file "$TMP_RC")
fi

echo "🚀 4/6 更新云函数代码 + 环境变量 ..."
(cd "$SCRIPT_DIR" && tcb fn code update qianan-api --dir ../qianan/server/deploy_pkg --config-file "$TMP_RC")

# code update 完成后函数会短暂进入 Updating 状态，此时 config update 会被
# UpdateFunctionConfiguration 拒绝（"当前函数处于Updating状态，无法进行此操作"）。
# 曾经因此静默丢失环境变量更新（代码新、配置旧），必须先等状态回落再推配置。
echo "⏳ 等待函数状态回落（code update → Updating → Deployment completed）..."
for i in $(seq 1 30); do
  STATE=$(tcb fn detail qianan-api 2>/dev/null | grep -o "Deployment completed\|Updating\|Update failed" | head -1 || true)
  case "$STATE" in
    "Deployment completed") echo "   函数已就绪（第 ${i} 次探测）"; break ;;
    *) sleep 4 ;;
  esac
  [ "$i" = "30" ] && echo "   ⚠️ 等待超时（120s），仍尝试更新配置"
done

# config update 有两处交互确认（y / Override 回车），用 expect 驱动
for attempt in 1 2 3; do
  OUT=$(TMP_RC="$TMP_RC" expect -c '
set timeout 300
spawn tcb config update fn qianan-api --all --config-file $env(TMP_RC)
expect {
  -re "Update all" { send "y\r"; exp_continue }
  -re "update method" { send "\r"; exp_continue }
  eof
}
' 2>&1 || true)
  echo "$OUT" | grep -E '✔|✖' || true
  if echo "$OUT" | grep -q "configuration updated successfully"; then
    break
  fi
  echo "   ⚠️ 配置更新第 ${attempt} 次未成功，${attempt}s 后重试..."
  sleep $((attempt * 5))
done
if ! echo "${OUT:-}" | grep -q "configuration updated successfully"; then
  echo "❌ 环境变量未能推送到云端 —— 云端可能仍用旧密钥，请手动执行："
  echo "   tcb config update fn qianan-api --all --config-file <物化后的配置>"
  exit 1
fi

if [ "$API_ONLY" = "1" ]; then
  echo "⏭️  5/6 跳过前端构建与托管部署（--api-only）"
else
  echo "🌐 5/6 清缓存构建并部署前端静态托管 ..."
  (cd "$WEB_DIR" && \
    rm -rf .next out && \
    NEXT_PUBLIC_API_BASE="$API_URL" \
    NEXT_PUBLIC_API_URL="$API_URL" \
    npm run build)
  (cd "$SCRIPT_DIR" && tcb hosting deploy "$WEB_DIR/out" -e "$ENV_ID" --yes)
fi

echo "🧪 6/6 公网冒烟 ..."
sleep 8
HEALTH=$(curl -s --max-time 70 "$API_URL/api/health" || true)
echo "health: $HEALTH"
case "$HEALTH" in
  *'"mock":false'*) echo "✅ 后端真实模式在线：$API_URL";;
  *) echo "⚠️ /api/health 未返回 mock:false（冷启动约 7-10s，稍后重试或 tcb fn log 排查）";;
esac
if [ "$API_ONLY" = "0" ]; then
  curl -s -o /dev/null -w "前端 / -> HTTP %{http_code}\n" --max-time 30 "$FRONT_URL/?cb=$RANDOM"
  echo "前端: $FRONT_URL"
fi
