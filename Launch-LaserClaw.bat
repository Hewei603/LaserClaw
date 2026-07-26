@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   LaserClaw 启动器
echo ============================================

rem ---- 前置检查:缺 Python / Node 时给出中文指引并停住,不再闪退 ----
where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo [错误] 没有检测到 Python。
  echo 请到 https://www.python.org/downloads/ 安装 Python 3.11 或更高版本,
  echo 安装时务必勾选 "Add python.exe to PATH",装完后重新双击本文件。
  echo.
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo.
  echo [错误] 没有检测到 Node.js。
  echo 请到 https://nodejs.org/ 安装 Node.js 22 LTS 版本,装完后重新双击本文件。
  echo.
  pause
  exit /b 1
)

rem ---- 首次运行:自动生成 .env 配置文件 ----
if not exist ".env" (
  if exist ".env.example" (
    copy /y ".env.example" ".env" >nul
    echo [提示] 已自动创建配置文件 .env(演示模式)。
    echo        想接入 AI 模型:用记事本打开根目录的 .env,按里面的中文说明填 key。
  )
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo 正在创建后端 Python 环境(首次运行需要几分钟)...
  py -3 -m venv backend\.venv
  if errorlevel 1 (
    echo.
    echo [错误] Python 虚拟环境创建失败。请截图此窗口内容寻求帮助。
    pause
    exit /b 1
  )
)

echo 正在安装/更新后端依赖(首次较慢,可能需要 5-10 分钟)...
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo.
  echo [错误] 后端依赖安装失败(常见原因:网络超时)。
  echo 可换用国内镜像后重试:先在此窗口运行一次
  echo   backend\.venv\Scripts\python.exe -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
  echo 再重新双击本文件;或截图此窗口内容寻求帮助。
  pause
  exit /b 1
)

echo 正在安装前端依赖...
pushd frontend
if not exist "node_modules" (
  call npm install
  if errorlevel 1 (
    popd
    echo.
    echo [错误] 前端依赖安装失败(常见原因:网络超时)。
    echo 可换用国内镜像后重试:npm config set registry https://registry.npmmirror.com
    pause
    exit /b 1
  )
)
popd

set DATABASE_URL=sqlite:///./laserclaw.db
set UPLOAD_DIR=./uploads
set AUTO_CREATE_TABLES=true
set VITE_API_URL=http://127.0.0.1:8000

if exist ".env" (
  echo 正在读取 .env 中的模型配置...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$allowed = @('AI_PROVIDER','OPENAI_API_KEY','OPENAI_MODEL','OPENAI_BASE_URL','ANTHROPIC_API_KEY','ANTHROPIC_MODEL','ANTHROPIC_MAX_TOKENS','ANTHROPIC_TEMPERATURE','DEEPSEEK_API_KEY','DEEPSEEK_MODEL','DEEPSEEK_BASE_URL','QWEN_API_KEY','QWEN_MODEL','QWEN_BASE_URL','ZHIPU_API_KEY','ZHIPU_MODEL','ZHIPU_BASE_URL','MOONSHOT_API_KEY','MOONSHOT_MODEL','MOONSHOT_BASE_URL','STRICT_PROVIDER','REQUIRE_AUTH','API_KEY'); Get-Content '.env' | ForEach-Object { if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') { $name = $matches[1].Trim(); $value = $matches[2].Trim(); if ($allowed -contains $name) { 'set ' + [char]34 + $name + '=' + $value + [char]34 } } }" > "%TEMP%\laserclaw_ai_env.cmd"
  call "%TEMP%\laserclaw_ai_env.cmd"
  del "%TEMP%\laserclaw_ai_env.cmd" >nul 2>nul
) else (
  set AI_PROVIDER=mock
  echo [提示] 没有 .env 配置文件,以演示模式启动(AI 输出为固定模板)。
)

echo 正在启动后端与前端(关闭弹出的两个窗口即可停止 LaserClaw)...
start "LaserClaw API" cmd /k "cd /d %CD%\backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "LaserClaw Web" cmd /k "cd /d %CD%\frontend && npm run dev -- --host 127.0.0.1 --port 5173"

echo 正在等待服务就绪(最多 60 秒)...
powershell -NoProfile -Command "for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -Uri 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1"
if errorlevel 1 (
  echo [提示] 服务启动比预期慢。浏览器打开后如果显示无法访问,请等几秒再刷新一次。
)
start "" "http://127.0.0.1:5173"

echo.
echo LaserClaw 已启动:http://127.0.0.1:5173
echo 本窗口可以关闭;停止 LaserClaw 请关闭另外两个黑色窗口。
pause
endlocal
