@echo off
cd /d "%~dp0"
title Hyperliquid logger
echo Starting... the dashboard addresses are printed below (Ctrl+C stops)
python app.py %*
echo.
echo The program has stopped.
pause
