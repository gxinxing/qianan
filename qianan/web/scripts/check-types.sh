#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "▶ 进入项目目录: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

echo "▶ 检查 TypeScript 配置..."
if [ ! -f tsconfig.json ]; then
    echo "✗ 未找到 tsconfig.json"
    exit 1
fi

echo "▶ 运行 tsc --noEmit..."
npx tsc --noEmit 2>&1 | head -80

EXIT_CODE=$?
echo "---"
echo "Type check exit code: $EXIT_CODE"

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ TypeScript 类型检查通过"
else
    echo "⚠️  TypeScript 类型检查发现错误（详见上方输出）"
fi

exit $EXIT_CODE
