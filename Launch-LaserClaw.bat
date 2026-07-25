@echo off
setlocal
cd /d "%~dp0"

echo Starting LaserClaw local web client...

if not exist "backend\.venv\Scripts\python.exe" (
  echo Creating backend virtual environment...
  py -3 -m venv backend\.venv
)

echo Installing backend dependencies...
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

echo Installing frontend dependencies...
pushd frontend
if not exist "node_modules" (
  npm install
)
popd

set DATABASE_URL=sqlite:///./laserclaw.db
set UPLOAD_DIR=./uploads
set AUTO_CREATE_TABLES=true
set VITE_API_URL=http://127.0.0.1:8000

if exist ".env" (
  echo Loading AI provider settings from .env...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$allowed = @('AI_PROVIDER','OPENAI_API_KEY','OPENAI_MODEL','OPENAI_BASE_URL','ANTHROPIC_API_KEY','ANTHROPIC_MODEL','ANTHROPIC_MAX_TOKENS','ANTHROPIC_TEMPERATURE','DEEPSEEK_API_KEY','DEEPSEEK_MODEL','DEEPSEEK_BASE_URL','QWEN_API_KEY','QWEN_MODEL','QWEN_BASE_URL','ZHIPU_API_KEY','ZHIPU_MODEL','ZHIPU_BASE_URL','MOONSHOT_API_KEY','MOONSHOT_MODEL','MOONSHOT_BASE_URL','STRICT_PROVIDER','REQUIRE_AUTH','API_KEY'); Get-Content '.env' | ForEach-Object { if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') { $name = $matches[1].Trim(); $value = $matches[2].Trim(); if ($allowed -contains $name) { 'set ' + [char]34 + $name + '=' + $value + [char]34 } } }" > "%TEMP%\laserclaw_ai_env.cmd"
  call "%TEMP%\laserclaw_ai_env.cmd"
  del "%TEMP%\laserclaw_ai_env.cmd" >nul 2>nul
) else (
  set AI_PROVIDER=mock
)

echo Launching API and web app. Close the opened windows to stop LaserClaw.
start "LaserClaw API" cmd /k "cd /d %CD%\backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "LaserClaw Web" cmd /k "cd /d %CD%\frontend && npm run dev -- --host 127.0.0.1 --port 5173"

timeout /t 5 >nul
start "" "http://127.0.0.1:5173"

endlocal
