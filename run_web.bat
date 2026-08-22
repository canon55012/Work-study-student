@echo off
chcp 65001 > nul
title Trusted Cloud AI Agent - Web

REM ------------------------------------------------------------
REM  Web launcher: starts MCP Server + web.py.
REM  (main.py runs the CMD version and never opens :5000)
REM
REM  Kept ASCII-only on purpose: cmd.exe under chcp 65001 can lose sync
REM  on multi-byte characters and silently swallow a whole line.
REM  All checks and messages live in scripts/start_web.py instead.
REM ------------------------------------------------------------

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [X] python not found. Install Python or add it to PATH.
    pause
    exit /b 1
)

python scripts\start_web.py

pause
