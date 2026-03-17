@echo off
setlocal

cd /d "%~dp0\.."

if not exist backend\.venv (
    echo ❌ 请先运行 scripts\setup.bat
    exit /b 1
)
if not exist frontend\node_modules (
    echo ❌ 请先运行 scripts\setup.bat
    exit /b 1
)

echo === 启动 StockScape ===

:: 后端
start "StockTerrain-Backend" /D backend .venv\Scripts\python main.py

:: 等待后端
echo 等待后端启动...
:wait_backend
timeout /t 1 /nobreak >nul
curl -sf http://localhost:8000/api/v1/health >nul 2>&1
if errorlevel 1 goto wait_backend
echo ✅ 后端: http://localhost:8000

:: 前端
start "StockScape-Frontend" /D frontend cmd /c "npm run dev"

echo ✅ 前端: http://localhost:3000
echo.
echo 关闭此窗口或按 Ctrl+C 停止
pause
