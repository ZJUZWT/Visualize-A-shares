#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=== StockTerrain 环境配置 ==="

# 检测 Python 3.10+
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi
PY_VER=$(python3 -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "❌ Python 版本 $PY_VER 过低，需要 3.10+"
    exit 1
fi
echo "✅ Python $PY_VER"

# 检测 Node.js 18+
if ! command -v node &>/dev/null; then
    echo "❌ 未找到 node，请先安装 Node.js 18+"
    exit 1
fi
echo "✅ Node.js $(node -v)"

# 后端环境
echo ""
echo "--- 配置后端环境 ---"
cd backend
if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo "  创建 .venv"
fi
.venv/bin/pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
echo "  依赖安装完成"
cd "$PROJECT_ROOT"

# 前端环境
echo ""
echo "--- 配置前端环境 ---"
cd frontend
npm install --silent
echo "  依赖安装完成"
cd "$PROJECT_ROOT"

# .env
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo ""
        echo "📝 已创建 .env，请编辑填入 API Key"
    fi
fi

echo ""
echo "=== 配置完成 ==="
echo "运行 scripts/start.sh 启动服务"
