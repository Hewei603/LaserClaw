@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   LaserClaw 启动器
echo ============================================

rem 注意:本文件中 if/else 括号块内的 echo 文本一律使用全角括号（），
rem 半角 ) 会被 cmd 当作块结束符导致整个脚本解析错乱。

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
    echo [提示] 已自动创建配置文件 .env（演示模式）。
    echo        想接入 AI 模型:用记事本打开根目录的 .env,按里面的中文说明填 key。
  )
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo 正在创建后端 Python 环境（首次运行需要几分钟）...
  py -3 -m venv backend\.venv
  if errorlevel 1 (
    echo.
    echo [错误] Python 虚拟环境创建失败。请截图此窗口内容寻求帮助。
    pause
    exit /b 1
  )
)

echo 正在安装/更新后端依赖（首次较慢,可能需要 5-10 分钟）...
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo.
  echo [错误] 后端依赖安装失败（常见原因:网络超时）。
  echo 可换用国内镜像后重试:先在此窗口运行一次
  echo   backend\.venv\Scripts\python.exe -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
  echo 再重新双击本文件;或截图此窗口内容寻求帮助。
  pause
  exit /b 1
)

rem 前端依赖每次都装:更新代码后可能新增依赖,node_modules 已最新时只需几秒。
echo 正在安装/更新前端依赖...
pushd frontend
call npm install --no-audit --no-fund
if errorlevel 1 (
  popd
  echo.
  echo [错误] 前端依赖安装失败（常见原因:网络超时）。
  echo 可换用国内镜像后重试:npm config set registry https://registry.npmmirror.com
  pause
  exit /b 1
)
popd

rem ---- 数据目录:实验数据与代码分离,更新/重装代码永远不会碰到数据 ----
rem 旧版本把数据存在代码文件夹里（backend\laserclaw.db）;后端启动时会自动
rem 把旧位置的数据一次性搬到这里,见 backend/app/data_migration.py。
set "LASERCLAW_DATA_DIR=%USERPROFILE%\LaserClaw-Data"
if not exist "%LASERCLAW_DATA_DIR%" mkdir "%LASERCLAW_DATA_DIR%"
set "LASERCLAW_DATA_DIR_FWD=%LASERCLAW_DATA_DIR:\=/%"
set "DATABASE_URL=sqlite:///%LASERCLAW_DATA_DIR_FWD%/laserclaw.db"
set "UPLOAD_DIR=%LASERCLAW_DATA_DIR%\uploads"
set "VECTOR_STORE_DIR=%LASERCLAW_DATA_DIR%\vector_store"
set AUTO_CREATE_TABLES=true
set VITE_API_URL=http://127.0.0.1:8000
echo [提示] 实验数据保存在 %LASERCLAW_DATA_DIR% （更新软件不会影响数据）。

if exist ".env" (
  echo 正在读取 .env 中的模型配置...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$allowed = @('AI_PROVIDER','OPENAI_API_KEY','OPENAI_MODEL','OPENAI_BASE_URL','ANTHROPIC_API_KEY','ANTHROPIC_MODEL','ANTHROPIC_MAX_TOKENS','ANTHROPIC_TEMPERATURE','DEEPSEEK_API_KEY','DEEPSEEK_MODEL','DEEPSEEK_BASE_URL','QWEN_API_KEY','QWEN_MODEL','QWEN_BASE_URL','ZHIPU_API_KEY','ZHIPU_MODEL','ZHIPU_BASE_URL','MOONSHOT_API_KEY','MOONSHOT_MODEL','MOONSHOT_BASE_URL','STRICT_PROVIDER','REQUIRE_AUTH','API_KEY'); Get-Content '.env' | ForEach-Object { if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') { $name = $matches[1].Trim(); $value = $matches[2].Trim(); if ($allowed -contains $name) { 'set ' + [char]34 + $name + '=' + $value + [char]34 } } }" > "%TEMP%\laserclaw_ai_env.cmd"
  call "%TEMP%\laserclaw_ai_env.cmd"
  del "%TEMP%\laserclaw_ai_env.cmd" >nul 2>nul
) else (
  set AI_PROVIDER=mock
  echo [提示] 没有 .env 配置文件,以演示模式启动（AI 输出为固定模板）。
)

rem ---- 关键一步:接管被旧进程占用的端口 ----
rem 旧的 LaserClaw 窗口如果还开着,新程序会启动失败,而浏览器仍连到旧代码上
rem ——用户完全无法察觉自己在用旧版。只结束命令行特征匹配 LaserClaw 的进程
rem （uvicorn app.main / vite / 本仓库路径）;其他程序占用端口时给出中文警告而不误杀。
echo 正在检查是否有旧的 LaserClaw 进程占用端口...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$repo = '%CD%'; foreach ($p in 8000,5173) { $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($procId in $conns) { $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue; if ($null -eq $proc) { continue }; $cmdline = (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $procId) -ErrorAction SilentlyContinue).CommandLine; if ($cmdline -and ($cmdline -like '*uvicorn app.main*' -or $cmdline -like '*vite*' -or $cmdline -like ('*' + $repo + '*'))) { Write-Output ('[提示] 端口 ' + $p + ' 上有旧的 LaserClaw 进程 (' + $proc.ProcessName + ', PID ' + $procId + '),正在自动关闭...'); Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } else { Write-Output ('[警告] 端口 ' + $p + ' 被其他程序占用 (' + $proc.ProcessName + '),LaserClaw 可能无法启动。请先关闭该程序再重新双击本文件。') } } }"

echo 正在启动后端与前端（关闭弹出的两个窗口即可停止 LaserClaw）...
start "LaserClaw API" cmd /k "cd /d %CD%\backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "LaserClaw Web" cmd /k "cd /d %CD%\frontend && npm run dev -- --host 127.0.0.1 --port 5173"

echo 正在等待服务就绪（最多 60 秒）...
powershell -NoProfile -Command "$ok = $false; for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2 | Out-Null; Invoke-WebRequest -Uri 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { Start-Sleep -Seconds 1 } }; if ($ok) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo [提示] 服务启动比预期慢。浏览器打开后如果显示无法访问,请等几秒再刷新一次。
)
start "" "http://127.0.0.1:5173"

echo.
echo LaserClaw 已启动:http://127.0.0.1:5173
echo 数据目录:%LASERCLAW_DATA_DIR%
echo 本窗口可以关闭;停止 LaserClaw 请关闭另外两个黑色窗口。
pause
endlocal
