# relaxASMR GUI

Tkinter 图形界面，用于 Rain 睡眠系列 loop 视频 → Reaper 子工程 → YouTube 物料 → 自动上传工作流。

## 依赖

- Python 3.10+
- `python3-tk`（Ubuntu/Debian: `sudo apt install python3-tk`）
- `ffmpeg` / `ffprobe`（画面与内嵌音轨分析、缩略图截帧）
- `numpy`（`analyze_video_audio.py`）
- `Pillow`（YouTube 缩略图合成：`pip install pillow`）
- **YouTube 上传**：`pip install -r scripts/video_upload/requirements.txt`
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

1. **导入 Loop 视频** — 选择 MP4，自动复制到 `assets/loop_video/rain_video/<MVI_xxxx>/`（记住上次选文件目录）
2. **新建 Reaper 子工程 + YouTube 物料** — 画面/音轨分析 → 配方与 `.rpp` → **同步生成** `output/material/<loop名>/`（`thumbnail.jpg` + `youtube.md`）；封面标题 **Rain Sounds for Sleep**，副标题仅地点，无 4K 角标；可「打开物料目录」
3. **打开 Reaper 工程** — 一键用 Windows/macOS Reaper 打开当前场景 `.rpp`
4. **上传到 YouTube** — 使用 YouTube Data API，从物料目录读取标题/描述/Tags，上传对应成片 MP4 并设置缩略图

**上传前置**：

1. Google Cloud OAuth 客户端 JSON 放到 `scripts/video_upload/config/`（见 [`scripts/video_upload/README.md`](../scripts/video_upload/README.md)）
2. 已完成第 2 步（含物料生成）
3. 已用 `export_mp4.sh` 将成片导出到子工程 `output/`（上传时按物料目录名匹配 MP4）
4. 首次点击上传会在浏览器完成 OAuth；令牌按账号保存在 `config/token_leo.json` / `token_leo_usa.json`

上传选项：可见性（unlisted / private / public）、标题/描述语言（en / zh）、**leo_usa** 勾选（默认 `leo` 账号）。

## WSL 说明

Reaper 在 Windows 侧运行，GUI 会通过 `cmd.exe` 调用 Windows 版 Reaper。

**YouTube OAuth（WSL）**：首次上传会在 **Windows 浏览器**打开 Google 授权页（非 `xdg-open`）；授权完成后自动回到 GUI。

本地偏好保存在 `gui/user_config.json`（已 gitignore）。
