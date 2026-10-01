@echo off
REM Lanceur Windows : double-clique. Installe tout au premier lancement, connecte Phantom si besoin, démarre le bot.
REM   start.bat --status   (ou --check, --sell-all, --once, --connect)
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist .venv (
  echo Installation (une seule fois^)...
  %PY% -m venv .venv || (echo Installe Python 3.10+ depuis https://www.python.org/downloads/ en cochant "Add to PATH" & pause & exit /b 1)
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\python -m pip install -q -r requirements-memecoin.txt
)
if "%~1"=="--connect" (
  .venv\Scripts\python -m memecoin_bot.connect
  pause
  exit /b
)
if not exist .env .venv\Scripts\python -m memecoin_bot.connect
if "%~1"=="" (
  .venv\Scripts\python -m memecoin_bot.main --check || (echo Corrige les erreurs ci-dessus ^(start.bat --connect pour reconfigurer^). & pause & exit /b 1)
)
.venv\Scripts\python -m memecoin_bot.main %*
pause
