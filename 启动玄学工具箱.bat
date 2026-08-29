@echo off
rem ============================================
rem  玄学工具箱 - 一键启动脚本
rem  Evander's Mysticism Tools Launcher
rem  双击本文件即可运行，无需打开 IDE
rem ============================================
setlocal
cd /d "%~dp0"

rem ---- 优先使用项目自带虚拟环境 ----
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "VENV_PYW=%~dp0.venv\Scripts\pythonw.exe"

if exist "%VENV_PY%" (
    set "PY=%VENV_PY%"
    set "PYW=%VENV_PYW%"
    goto :check
)

rem ---- 未找到虚拟环境，尝试系统 Python ----
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python 解释器。
    echo        请安装 Python 3.8+（安装时勾选 Add to PATH），
    echo        或在项目目录执行: python -m venv .venv
    pause
    exit /b 1
)
set "PY=python"
set "PYW=pythonw"

:check
rem ---- 检查核心依赖 ----
"%PY%" -c "import PySide6, ephem, openai" >nul 2>nul
if errorlevel 1 (
    echo [提示] 缺少依赖，正在安装 requirements.txt ...
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试。
        echo        或手动执行: "%PY%" -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

rem ---- 预检程序可正常导入 ----
"%PY%" -c "import main" >nul 2>nul
if errorlevel 1 (
    echo [错误] 程序启动失败，请检查 Python 环境或代码。
    pause
    exit /b 1
)

rem ---- 后台启动 GUI（无控制台窗口）----
start "" "%PYW%" main.py
exit /b 0
