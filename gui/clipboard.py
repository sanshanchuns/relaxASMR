"""Tk Text 复制/粘贴与 WSL 剪贴板兼容（同 economist/gui/widgets.py）。"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

logger = logging.getLogger(__name__)

_WIN_SYSTEM32 = Path("/mnt/c/Windows/System32")
_WIN_POWERSHELL = _WIN_SYSTEM32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"
_WIN_CLIP = _WIN_SYSTEM32 / "clip.exe"

# Tk X11 CLIPBOARD is unsafe for large payloads on WSLg/VcXsrv.
_TK_CLIPBOARD_SAFE_CHARS = 8_192


def _resolve_cmd(*names: str, fallbacks: list[Path] | None = None) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for path in fallbacks or []:
        if path.is_file():
            return str(path)
    return None


def _is_wsl() -> bool:
    if Path("/mnt/c/Windows").is_dir():
        return True
    if shutil.which("powershell.exe") or shutil.which("clip.exe"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _windows_clipboard_write(content: str) -> bool:
    """Write Windows host clipboard from WSL."""
    ps = _resolve_cmd("powershell.exe", "pwsh.exe", fallbacks=[_WIN_POWERSHELL])

    if ps:
        ps_cmd = (
            "$bytes = New-Object byte[] 0; "
            "$stdin = [Console]::OpenStandardInput(); "
            "$ms = New-Object System.IO.MemoryStream; "
            "$stdin.CopyTo($ms); $bytes = $ms.ToArray(); "
            "if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) { "
            "  $t = [Text.Encoding]::Unicode.GetString($bytes, 2, $bytes.Length - 2) "
            "} else { "
            "  $t = [Text.Encoding]::UTF8.GetString($bytes) "
            "}; "
            "Set-Clipboard -Value $t"
        )
        try:
            payload = b"\xff\xfe" + content.encode("utf-16le")
            proc = subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                input=payload,
                capture_output=True,
                timeout=20,
            )
            if proc.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("powershell clipboard write failed: %s", exc)

        try:
            win_tmp_dir = Path("/mnt/c/Windows/Temp")
            if not win_tmp_dir.is_dir():
                win_tmp_dir = Path("/mnt/c/Users/Public")
            if win_tmp_dir.is_dir():
                tmp_path = win_tmp_dir / f"relax_clip_{os.getpid()}.txt"
                tmp_path.write_text(content, encoding="utf-8-sig")
                rel = tmp_path.as_posix().removeprefix("/mnt/c/")
                win_path = "C:\\" + rel.replace("/", "\\")
                file_cmd = (
                    f"$t = Get-Content -LiteralPath '{win_path}' -Raw -Encoding UTF8; "
                    "Set-Clipboard -Value $t"
                )
                try:
                    proc = subprocess.run(
                        [ps, "-NoProfile", "-NonInteractive", "-Command", file_cmd],
                        capture_output=True,
                        timeout=20,
                    )
                    if proc.returncode == 0:
                        return True
                finally:
                    tmp_path.unlink(missing_ok=True)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("powershell tempfile clipboard failed: %s", exc)

    if content.isascii():
        clip = _resolve_cmd("clip.exe", fallbacks=[_WIN_CLIP])
        if clip:
            try:
                proc = subprocess.run(
                    [clip],
                    input=content.encode("utf-8"),
                    capture_output=True,
                    timeout=15,
                )
                if proc.returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError) as exc:
                logger.debug("clip.exe helper failed: %s", exc)
    return False


def _linux_native_clipboard_write(content: str) -> bool:
    try:
        wl_copy = shutil.which("wl-copy")
        if wl_copy:
            proc = subprocess.run(
                [wl_copy],
                input=content.encode("utf-8"),
                capture_output=True,
                timeout=5,
            )
            if proc.returncode == 0:
                return True
        if len(content) > 16_384:
            return False
        xclip = shutil.which("xclip")
        if xclip:
            proc = subprocess.run(
                [xclip, "-selection", "clipboard", "-i"],
                input=content.encode("utf-8"),
                capture_output=True,
                timeout=5,
            )
            if proc.returncode == 0:
                return True
        xsel = shutil.which("xsel")
        if xsel and len(content) <= 16_384:
            proc = subprocess.run(
                [xsel, "--clipboard", "--input"],
                input=content.encode("utf-8"),
                capture_output=True,
                timeout=5,
            )
            if proc.returncode == 0:
                return True
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("linux clipboard helper failed: %s", exc)
    return False


def _linux_clipboard_write(content: str) -> bool:
    if _is_wsl():
        return _windows_clipboard_write(content)
    return _linux_native_clipboard_write(content)


def _windows_clipboard_read() -> str:
    ps = _resolve_cmd("powershell.exe", "pwsh.exe", fallbacks=[_WIN_POWERSHELL])
    if not ps:
        return ""
    try:
        win_tmp_dir = Path("/mnt/c/Windows/Temp")
        if not win_tmp_dir.is_dir():
            win_tmp_dir = Path("/mnt/c/Users/Public")
        if not win_tmp_dir.is_dir():
            return ""
        tmp_path = win_tmp_dir / f"relax_clip_read_{os.getpid()}.txt"
        rel = tmp_path.as_posix().removeprefix("/mnt/c/")
        win_path = "C:\\" + rel.replace("/", "\\")
        cmd = f"Get-Clipboard | Set-Content -LiteralPath '{win_path}' -Encoding UTF8"
        try:
            proc = subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                timeout=8,
            )
            if proc.returncode != 0 or not tmp_path.is_file():
                return ""
            return tmp_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        finally:
            tmp_path.unlink(missing_ok=True)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("powershell Get-Clipboard failed: %s", exc)
    return ""


def _resolve_event_widget(widget: object) -> tk.Misc | None:
    """``bind_class`` 偶发把 ``event.widget`` 传成路径字符串，需解析回控件。"""
    if widget is None:
        return None
    if isinstance(widget, tk.Misc):
        return widget
    if isinstance(widget, str):
        root = None
        try:
            root = tk._get_default_root()  # type: ignore[attr-defined]  # noqa: SLF001
        except Exception:
            root = getattr(tk, "_default_root", None)
        if root is not None:
            try:
                return root.nametowidget(widget)
            except (tk.TclError, KeyError, AttributeError):
                return None
    return None


def _get_safe_clipboard(master: tk.Misc | None) -> str:
    widget = _resolve_event_widget(master) if not isinstance(master, tk.Misc) else master
    if widget is None and isinstance(master, tk.Misc):
        widget = master

    try:
        if widget is not None:
            root = widget.winfo_toplevel()
            hold = getattr(root, "_relaxasmr_clipboard_hold", None)
            if hold:
                return hold
    except Exception:
        pass

    if _is_wsl():
        val = _windows_clipboard_read()
        if val:
            return val

    for candidate in (widget, getattr(tk, "_default_root", None)):
        if candidate is None or not hasattr(candidate, "clipboard_get"):
            continue
        try:
            return candidate.clipboard_get()
        except (tk.TclError, AttributeError):
            continue
    return ""


def _safe_paste_event(event: tk.Event) -> str:
    widget = _resolve_event_widget(event.widget)
    text = _get_safe_clipboard(widget)
    if not text:
        return "break"
    if widget is None:
        return "break"
    try:
        if isinstance(widget, tk.Text):
            if widget.tag_ranges(tk.SEL):
                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            widget.insert(tk.INSERT, text)
            widget.see(tk.INSERT)
        elif isinstance(widget, (tk.Entry, ttk.Entry)):
            try:
                if widget.selection_present():
                    widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except (tk.TclError, AttributeError):
                pass
            widget.insert(tk.INSERT, text)
    except (tk.TclError, AttributeError):
        pass
    return "break"


def setup_global_clipboard_safety(root: tk.Misc) -> None:
    """全局安全粘贴，避免 WSL 下 X connection to :0 broken。"""
    for cls_name in ("Text", "Entry", "TEntry", "TCombobox"):
        try:
            root.bind_class(cls_name, "<<Paste>>", _safe_paste_event)
            root.bind_class(cls_name, "<Control-v>", _safe_paste_event)
            root.bind_class(cls_name, "<Control-V>", _safe_paste_event)
        except tk.TclError:
            pass


def _copy_to_clipboard(
    master: tk.Misc, content: str, *, text_widget: tk.Text | None = None
) -> bool:
    if not content:
        return False
    root = master.winfo_toplevel()
    host_ok = False

    if sys.platform == "linux":
        host_ok = _linux_clipboard_write(content)
    elif sys.platform == "win32":
        host_ok = _windows_clipboard_write(content)

    try:
        root._relaxasmr_clipboard_hold = content  # noqa: SLF001
    except tk.TclError:
        pass

    tk_ok = False
    use_tk_clipboard = not host_ok
    if use_tk_clipboard and _is_wsl() and len(content) > _TK_CLIPBOARD_SAFE_CHARS:
        use_tk_clipboard = False
    if use_tk_clipboard:
        try:
            root.clipboard_clear()
            root.clipboard_append(content)
            root.update_idletasks()
            tk_ok = True
        except tk.TclError:
            tk_ok = False

    if text_widget is not None:
        try:
            text_widget.focus_set()
        except tk.TclError:
            pass
    return host_ok or tk_ok


def _copy_text_selection(text: tk.Text, master: tk.Misc) -> bool:
    try:
        content = text.get(tk.SEL_FIRST, tk.SEL_LAST)
    except tk.TclError:
        return False
    if not content:
        return False
    return _copy_to_clipboard(master, content, text_widget=text)


def setup_editable_text_copy(text: tk.Text, master: tk.Misc) -> None:
    """可编辑 Text：拦截复制，走 Windows 宿主剪贴板（WSL 可多次复制）。"""

    def _on_copy(_event: tk.Event | None = None) -> str:
        try:
            if text.tag_ranges(tk.SEL):
                _copy_text_selection(text, master)
        except tk.TclError:
            pass
        return "break"

    text.bind("<Control-c>", _on_copy)
    text.bind("<Control-C>", _on_copy)
    text.bind("<Control-Insert>", _on_copy)
    text.bind("<<Copy>>", _on_copy)


def setup_copyable_readonly_text(
    text: tk.Text,
    master: tk.Misc,
    *,
    export_selection: bool = True,
) -> None:
    """只读 Text：可选中/复制/右键菜单，禁止键入。"""
    text.configure(
        exportselection=export_selection,
        cursor="xterm",
        insertwidth=0,
        takefocus=True,
    )

    def _on_click(_event: tk.Event) -> None:
        try:
            text.focus_set()
        except tk.TclError:
            pass

    def _focus_on_drag(_event: tk.Event) -> None:
        try:
            text.focus_set()
        except tk.TclError:
            pass

    def _select_all() -> None:
        text.tag_add(tk.SEL, "1.0", tk.END)
        text.mark_set(tk.INSERT, "1.0")
        text.see(tk.INSERT)

    def _on_copy(_event: tk.Event | None = None) -> str:
        try:
            if text.tag_ranges(tk.SEL):
                _copy_text_selection(text, master)
            else:
                content = text.get("1.0", tk.END).strip()
                _copy_to_clipboard(master, content, text_widget=text)
        except tk.TclError:
            pass
        return "break"

    def _on_select_all(_event: tk.Event | None = None) -> str:
        _select_all()
        return "break"

    def _block_typing(event: tk.Event) -> str | None:
        sym = event.keysym.lower()
        state = event.state
        ctrl = bool(state & 0x4) or bool(state & 0x8) or bool(state & 0x200)
        if ctrl and sym in {"c", "a", "insert"}:
            if sym == "a":
                return _on_select_all(event)
            return _on_copy(event)
        if sym in {
            "left",
            "right",
            "up",
            "down",
            "home",
            "end",
            "prior",
            "next",
            "shift_l",
            "shift_r",
            "control_l",
            "control_r",
        }:
            return None
        return "break"

    text.bind("<Button-1>", _on_click, add="+")
    text.bind("<B1-Motion>", _focus_on_drag, add="+")
    text.bind("<Control-c>", _on_copy)
    text.bind("<Control-C>", _on_copy)
    text.bind("<Control-Insert>", _on_copy)
    text.bind("<Control-a>", _on_select_all)
    text.bind("<Control-A>", _on_select_all)
    text.bind("<<Copy>>", _on_copy)
    text.bind("<Key>", _block_typing)

    menu = tk.Menu(text, tearoff=0)
    menu.add_command(label="复制", command=lambda: _on_copy())
    menu.add_command(label="全选", command=_select_all)

    def _popup_menu(event: tk.Event) -> None:
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    text.bind("<Button-3>", _popup_menu)


__all__ = [
    "setup_copyable_readonly_text",
    "setup_editable_text_copy",
    "setup_global_clipboard_safety",
]
