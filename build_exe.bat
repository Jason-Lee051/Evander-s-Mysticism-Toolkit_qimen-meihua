@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   玄学工具箱 - 打包构建
echo ============================================

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [1/2] 正在安装 PyInstaller...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
) else (
    echo [1/2] PyInstaller 已安装
)

echo [2/2] 正在构建（需要几分钟）...
".venv\Scripts\pyinstaller.exe" mysticism_tools.spec --noconfirm
if errorlevel 1 (
    echo.
    echo 构建失败，请检查上方错误信息。
    pause
    exit /b 1
)

echo.
echo 构建完成！输出目录：dist\玄学工具箱\
echo 可将该文件夹压缩为 zip 分发。
pause
