#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 检查环境
[ -d backend/.venv ] || { echo "❌ 请先运行 scripts/setup.sh"; exit 1; }
[ -d frontend/node_modules ] || { echo "❌ 请先运行 scripts/setup.sh"; exit 1; }

echo "=== 启动 StockScape ==="

# 后端
cd "$PROJECT_ROOT/backend"
.venv/bin/python main.py &
BACKEND_PID=$!
cd "$PROJECT_ROOT"

# 等待后端就绪
echo "等待后端启动..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
        echo "✅ 后端: http://localhost:8000"
        break
    fi
    sleep 1
done

# 前端
cd "$PROJECT_ROOT/frontend"
npm run dev &
FRONTEND_PID=$!
cd "$PROJECT_ROOT"

echo "✅ 前端: http://localhost:3000"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 优雅关闭
cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "已停止"
}
trap cleanup INT TERM
wait
