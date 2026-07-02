# relaxASMR GUI

Tkinter 图形界面，用于 Rain 睡眠系列 loop 视频 → Reaper 子工程工作流。

## 依赖

- Python 3.10+
- `python3-tk`（Ubuntu/Debian: `sudo apt install python3-tk`）
- `ffmpeg` / `ffprobe`（画面与内嵌音轨分析）
- `numpy`（`analyze_video_audio.py`）
- Reaper（打开 `.rpp`；可选填写可执行文件路径）

## 启动

在仓库根目录：

```bash
python3 -m gui
```

或：

```bash
python3 gui/app.py
```

## 功能

1. **导入 Loop 视频** — 选择 MP4，自动复制到 `assets/loop_video/rain_video/<MVI_xxxx>/`
2. **新建 Reaper 子工程** — 画面首帧启发 + 内嵌音轨七层分析 → 配方与声源选取理由 → 生成 `video_analysis.md`、`asmr_config.lua`、`.rpp`
3. **打开 Reaper 工程** — 一键用 Reaper 打开当前场景对应的 `.rpp`

**WSL**：Reaper 在 Windows 侧运行，GUI 会通过 `cmd.exe` 调用 Windows 版 Reaper，并使用 `\\wsl.localhost\...` 路径打开工程（不会走 Linux 的 `xdg-open`）。启动时会自动探测常见安装路径（含 `D:\Program Files\REAPER (x64)\reaper.exe`）；若未找到，请手动填写 Windows 路径。

本地偏好保存在 `gui/user_config.json`（已 gitignore）：`last_video_dir`（选 MP4 默认目录）、`reaper_exe` 等。
