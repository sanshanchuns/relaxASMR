# 在 Windows 桌面创建 relaxASMR GUI 快捷方式（无 CMD 窗口）
# 用法:
#   powershell.exe -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\acele\workspace\relaxASMR\scripts\create_gui_shortcut.ps1"

$ErrorActionPreference = "Stop"

$LocalDir = Join-Path $env:LOCALAPPDATA "relaxASMR"
$LocalVbs = Join-Path $LocalDir "launch_gui.vbs"
$LocalBat = Join-Path $LocalDir "launch_gui.bat"
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "relaxASMR GUI.lnk"

$VbsContent = @"
Set shell = CreateObject("WScript.Shell")
cmd = "wsl.exe -d Ubuntu -u acele bash -lc ""cd /home/acele/workspace/relaxASMR && /home/acele/.pyenv/shims/python -m gui"""
shell.Run cmd, 0, False
"@

$BatContent = @"
@echo off
title relaxASMR GUI
wsl.exe -d Ubuntu -u acele bash -lc "cd /home/acele/workspace/relaxASMR && /home/acele/.pyenv/shims/python -m gui"
if errorlevel 1 pause
"@

New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
Set-Content -Path $LocalVbs -Value $VbsContent -Encoding ASCII
Set-Content -Path $LocalBat -Value $BatContent -Encoding ASCII

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $LocalVbs
$Shortcut.WorkingDirectory = $LocalDir
$Shortcut.WindowStyle = 1
$Shortcut.Description = "启动 relaxASMR GUI (python -m gui)"
$Shortcut.Save()

Write-Host "已写入静默启动脚本: $LocalVbs"
Write-Host "已写入调试启动脚本: $LocalBat"
Write-Host "已创建桌面快捷方式: $ShortcutPath"
