@echo off
chcp 65001 >nul
echo ====================================
echo   语音 AI 助手 - 悬浮球启动器
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

REM 关闭已有的悬浮球进程
taskkill /F /IM python.exe >nul 2>&1

REM 启动悬浮球
echo [INFO] 正在启动悬浮球...
echo [INFO] 工作目录: %~dp0
echo.
echo [INFO] 提示：
echo    - 说"小助手"唤醒语音助手
echo    - 点击悬浮球展开聊天面板
echo    - 右键悬浮球退出程序
echo ====================================
echo.

cd /d %~dp0
python widget.py
