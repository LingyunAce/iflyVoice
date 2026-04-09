@echo off
echo ====================================
echo   中文语音识别系统 - 本地服务器启动器
echo ====================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未检测到Python环境
    echo.
    echo 请选择以下方式运行：
    echo 1. 安装Python 3.x (https://python.org)
    echo 2. 直接使用Chrome/Edge浏览器打开 index.html
    echo 3. 使用其他本地服务器工具
    echo.
    pause
    exit /b
)

echo ✅ Python环境检测成功
echo.

REM 启动HTTP服务器
echo 🚀 正在启动本地HTTP服务器...
echo 📁 服务器根目录: %~dp0
echo 🌐 访问地址: http://localhost:8000
echo.
echo 💡 提示：
echo    - 按 Ctrl+C 停止服务器
echo    - 请使用 Chrome 或 Edge 浏览器访问
echo    - 首次使用需要允许麦克风权限
echo.
echo ====================================
echo.

REM 使用Python启动HTTP服务器
python -m http.server 8000

REM 如果Python命令失败，尝试python3
if %errorlevel% neq 0 (
    python3 -m http.server 8000
)

echo.
echo 服务器已停止
echo.
pause