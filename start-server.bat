@echo off
chcp 65001 >nul
echo ====================================
echo   语音 AI 助手 - 服务器启动器
echo ====================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未检测到Python环境
    echo.
    echo 请安装 Python 3.x: https://python.org
    pause
    exit /b
)

echo [OK] Python 环境检测成功
echo.

REM 启动代理服务器
echo [INFO] 正在启动服务器...
echo [INFO] 服务器根目录: %~dp0
echo [INFO] 访问地址: http://localhost:18766
echo.
echo [INFO] 提示：
echo    - 按 Ctrl+C 停止服务器
echo    - 请使用 Chrome 或 Edge 浏览器访问
echo    - 首次使用需要允许麦克风权限
echo ====================================
echo.

cd /d %~dp0
python server.py
