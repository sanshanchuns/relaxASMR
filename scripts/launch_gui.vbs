Set shell = CreateObject("WScript.Shell")
wsl = shell.ExpandEnvironmentStrings("%SystemRoot%\System32\wsl.exe")
cmd = """" & wsl & """ -d Ubuntu -u acele bash -lc ""cd /home/acele/workspace/relaxASMR && /home/acele/.pyenv/shims/python -m gui"""
shell.Run cmd, 0, False
