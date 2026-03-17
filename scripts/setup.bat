@echo off
setlocal

cd /d "%~dp0\.."

echo === StockScape 环境配置 ===

:: 检测 Python
where python >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 python，请先安装 Python 3.10+
    exit /b 1
)
echo ✅ Python 已安装

:: 检测 Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 node，请先安装 Node.js 18+
    exit /b 1
)
echo ✅ Node.js 已安装

:: 后端环境
echo.
echo --- 配置后端环境 ---
cd backend
if not exist .venv (
    python -m venv .venv
    echo   创建 .venv
)
.venv\Scripts\pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
echo   依赖安装完成
cd ..

:: 前端环境
echo.
echo --- 配置前端环境 ---
cd frontend
call npm install --silent
echo   依赖安装完成
cd ..

:: .env
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo.
        echo 📝 已创建 .env，请编辑填入 API Key
    )
)

echo.
echo === 配置完成 ===
echo 运行 scripts\start.bat 启动服务
