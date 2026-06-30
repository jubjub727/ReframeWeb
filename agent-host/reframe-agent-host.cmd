@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "HOST_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"

if not exist "%HOST_PYTHON%" (
  echo Agent Host virtual environment not found at:
  echo   %HOST_PYTHON%
  echo.
  echo Run this first from agent-host:
  echo   uv sync
  exit /b 1
)

set "PYTHONPATH=%SCRIPT_DIR%src;%PYTHONPATH%"
"%HOST_PYTHON%" -m reframe_agent_host %*
