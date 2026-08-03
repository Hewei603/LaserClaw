@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   LaserClaw 更新器
echo ============================================
echo.
echo 提示:实验数据保存在 %USERPROFILE%\LaserClaw-Data,更新不会影响数据。
echo.

rem ---- 先停掉正在运行的 LaserClaw,避免更新后旧进程继续服务旧代码 ----
echo 正在关闭正在运行的 LaserClaw...
powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($p in 8000,5173) { $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($procId in $conns) { $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue; if ($null -ne $proc -and $proc.ProcessName -match '^(python|pythonw|node|uvicorn)$') { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } } }"

rem ---- 有 git 就拉最新代码;没有就给出人工路径 ----
where git >nul 2>nul
if errorlevel 1 goto :no_git
if not exist ".git" goto :no_git

echo 正在从 GitHub 拉取最新代码...
git pull --ff-only
if errorlevel 1 (
  echo.
  echo [错误] 自动更新失败(常见原因:网络不通,或本地文件被改动过)。
  echo 请截图此窗口内容找维护者;或让维护者发一份新版压缩包,
  echo 解压到一个新文件夹后直接双击其中的 Launch-LaserClaw.bat
  echo (实验数据在 %USERPROFILE%\LaserClaw-Data,不在代码文件夹里,不会丢)。
  echo.
  pause
  exit /b 1
)

echo.
echo 更新完成!正在为你启动新版本...
start "" "%~dp0Launch-LaserClaw.bat"
exit /b 0

:no_git
echo.
echo [提示] 这台电脑没有安装 Git,或此文件夹不是通过 Git 下载的,无法自动更新。
echo 更新方法:让维护者发一份新版压缩包,解压到一个新文件夹,
echo 然后双击其中的 Launch-LaserClaw.bat 即可。
echo 实验数据保存在 %USERPROFILE%\LaserClaw-Data(不在代码文件夹里),不会丢失。
echo.
pause
exit /b 0
