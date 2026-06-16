@echo off
REM ============================================================================
REM  Launch Sunny in serve mode and KEEP her running (auto-restart on crash).
REM
REM  To start her now:        double-click this file.
REM  To auto-start at login:  press Win+R, type  shell:startup , press Enter,
REM                           then drop a SHORTCUT to this file into that folder.
REM
REM  Output is written to sunny.log in this folder. To stop her, close this
REM  window. (.env is loaded automatically — no setup line needed.)
REM ============================================================================
cd /d "%~dp0"
title Sunny
:loop
echo [%date% %time%] starting Sunny... >> sunny.log
".venv\Scripts\python.exe" -m sunny.main serve >> sunny.log 2>&1
echo [%date% %time%] Sunny exited (code %errorlevel%); restarting in 10s... >> sunny.log
timeout /t 10 /nobreak >nul
goto loop
