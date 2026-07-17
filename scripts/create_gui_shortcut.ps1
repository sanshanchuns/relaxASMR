# Create relaxASMR GUI desktop shortcut.
# Primary: direct wsl.exe (most reliable for WSLg GUI).
# Backup:  launch_gui.vbs (silent, no console flash).

$ErrorActionPreference = "Stop"

$LocalDir = Join-Path $env:LOCALAPPDATA "relaxASMR"
$LocalVbs = Join-Path $LocalDir "launch_gui.vbs"
$LocalBat = Join-Path $LocalDir "launch_gui.bat"
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "relaxASMR GUI.lnk"
$Wsl = Join-Path $env:SystemRoot "System32\wsl.exe"
$BashCmd = "cd /home/acele/workspace/relaxASMR && /home/acele/.pyenv/shims/python -m gui"

$VbsContent = @"
Set shell = CreateObject("WScript.Shell")
wsl = shell.ExpandEnvironmentStrings("%SystemRoot%\System32\wsl.exe")
cmd = """" & wsl & """ -d Ubuntu -u acele bash -lc ""$BashCmd"""
shell.Run cmd, 0, False
"@

$BatContent = @"
@echo off
cd /d "%LOCALAPPDATA%\relaxASMR"
"%SystemRoot%\System32\wsl.exe" -d Ubuntu -u acele bash -lc "$BashCmd"
if errorlevel 1 pause
"@

New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
Set-Content -Path $LocalVbs -Value $VbsContent -Encoding ASCII
Set-Content -Path $LocalBat -Value $BatContent -Encoding ASCII

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $LocalVbs
$Shortcut.Arguments = ""
$Shortcut.WorkingDirectory = $LocalDir
$Shortcut.WindowStyle = 1
$Shortcut.Description = "Launch relaxASMR GUI"
$Shortcut.Save()

Write-Host "Shortcut -> VBS (silent)"
Write-Host "VBS: $LocalVbs"
Write-Host "BAT debug: $LocalBat"
Write-Host "Or double-click VBS directly if LNK fails"
