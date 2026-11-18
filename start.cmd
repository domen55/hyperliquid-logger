@echo off
cd /d "%~dp0"
title Hyperliquid logger
echo Dashboard: http://127.0.0.1:8765   (Ctrl+C stops)
python app.py %*
echo.
echo The program has stopped.
pause
