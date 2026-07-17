@echo off
title relaxASMR GUI
wsl.exe -d Ubuntu -u acele bash -lc "cd /home/acele/workspace/relaxASMR && /home/acele/.pyenv/shims/python -m gui"
if errorlevel 1 pause
