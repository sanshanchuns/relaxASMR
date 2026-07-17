Set shell = CreateObject("WScript.Shell")
cmd = "wsl.exe -d Ubuntu -u acele bash -lc ""cd /home/acele/workspace/relaxASMR && /home/acele/.pyenv/shims/python -m gui"""
shell.Run cmd, 0, False
