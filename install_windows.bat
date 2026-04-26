@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PYTHON_CMD="

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PYTHON_CMD=py -3"
  goto run
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PYTHON_CMD=python"
  goto run
)

echo Claude Desktop 中文补丁（Windows）
echo.
echo 未找到 Python 3。
echo 请先安装 Python 3，并确保以下任一命令可用：
echo   1. py -3
echo   2. python
echo.
echo 或者手动在终端执行：
echo   py -3 patch_claude_zh_cn.py --launch
echo.
pause
exit /b 1

:run
echo Claude Desktop 中文补丁（Windows）
echo 目录: %SCRIPT_DIR%
echo.
pushd "%SCRIPT_DIR%"
call %PYTHON_CMD% patch_claude_zh_cn.py --launch %*
set "STATUS=%ERRORLEVEL%"
popd

echo.
if not "%STATUS%"=="0" (
  echo 安装失败，错误码: %STATUS%
) else (
  echo 安装完成。
)
echo.
pause
exit /b %STATUS%
