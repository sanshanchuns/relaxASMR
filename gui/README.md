# relaxASMR GUI

Tkinter 图形界面，用于 Rain 睡眠系列 loop 视频 → Reaper 子工程 → YouTube 物料 → 自动上传工作流。

## 依赖

- Python 3.10+
- `python3-tk`（Ubuntu/Debian: `sudo apt install python3-tk`）
- `ffmpeg` / `ffprobe`（画面与内嵌音轨分析、缩略图截帧）
- **画面 CLIP 分析**（步骤 1 九宫格推荐）：
  ```bash
  pip install transformers Pillow
  # 按 GPU 选 torch（勿把主机 venv 整包拷到协作机）：
  # RTX 50 系 Blackwell（5060 等）— 必须 cu128+：
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
  # RTX 40 系（4060 等）：
  pip install torch torchvision
  ```
  详见 [`scripts/video_analysis/requirements.txt`](../scripts/video_analysis/requirements.txt)
- **VLM（Gemini）**：`pip install google-genai`；并配置 `GEMINI_API_KEY`（或写入 `~/.zshrc` 的 `export GEMINI_API_KEY=...`）
- `numpy`（`analyze_video_audio.py`）
- `Pillow`（已含于上一行 requirements；YouTube 缩略图合成亦需）
- **YouTube 上传**：`pip install -r scripts/video_upload/requirements.txt`
- Reaper（打开 `.rpp`；可选填写可执行文件路径）
- **「我的数据」/「爆款分析」两个分析 Tab**：
  - `pip install google-api-python-client requests`（`google-api-python-client` 已随「YouTube 上传」依赖装好）
  - 环境变量 `YOUTUBE_DATA_API_KEY`（YouTube Data API v3 key，用于频道/播放列表/视频/搜索等公开数据查询）
  - 「我的数据」解析自己频道 ID 时复用 `scripts/video_upload/config/token_leo.json`（即 leo / ace.leo.zhu@gmail.com 账号的已授权 OAuth token；若订阅数被频道设置隐藏，也会用它兜底读取真实订阅数）——需先在「上传 YouTube」步骤完成过一次授权
  - 「爆款分析」的 LLM 优点分析复用 `agy/`（Antigravity Cloud Code Gemini，方案同 `../economist/agy`）：需要 `agy/credentials.json`（Google OAuth refresh token，**不要提交到 git**）

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

1. **导入 Loop 视频** — 选择 MP4；可选「封面加雨效」（默认勾选）；可选「前缀视频」（只出现一次，加在 loop 前面）
2. **选择四轨声音库** — CLIP/VLM 推荐 `1_rain` 候选，各轨点选 WAV
3. **新建 Reaper 工程** — GUI 选音 → 内存构建配置 → 直接生成 `.rpp`（不写配置文件）
4. **导出音频与合成视频** — 一键混音、合成 MP4；若步骤 1 选了前缀视频，成片为「前缀一次 + loop 循环」
5. **上传到 YouTube** — 从物料目录读取元数据并上传成片

### 顶部 Tab 结构

| 顶部 Tab | 子 Tab |
|----------|--------|
| **工作流** | —（上面的步骤 1–5） |
| **数据分析** | 我的数据、爆款分析 |
| **素材库** | 视频、rain boom、impact、random、wildlife |
| **AIGC** | 图生视频 / 文生视频 / 旧 |

### 数据分析 Tab

| 子 Tab | 数据来源 | 功能 |
|-----|----------|------|
| **我的数据** | `YOUTUBE_DATA_API_KEY` + `agy`（LLM） | 展示自有频道（ace.leo.zhu@gmail.com）订阅人数、总视频数；视频按 YouTube 播放列表（系列）分组，每组内按播放量降序排列，宫格展示封面+标题（超长标题省略号），未加入任何播放列表的视频归入「未分类」；可对单个视频发起 LLM「优劣分析」（同时指出优点和不足，给改进建议） |
| **爆款分析** | `YOUTUBE_DATA_API_KEY` + `agy`（LLM） | 关键词默认「leaf rain」，可在输入框自定义（逗号分隔可搜多个），围绕关键词搜索同类高赞/高评论/高观看的爆款视频，按作者分组宫格展示，组内按「日均播放量」（归一化，识别快速增长的黑马）排序展示 Top 10；点击视频预览+可发起 LLM（Gemini，含封面图）分析爆款优点；点击作者查看其订阅人数/注册时间/总观看次数；每个分组标题栏右上角「✕」可删除该分组，删除后自动从预备池里补一个新分组（优先选「总播放量不高但增速很快」的黑马作者） |

两个子 Tab 只负责左侧宫格；预览缩略图、LLM 分析结果、「在浏览器中播放」按钮统一渲染在应用最外层的**右半边**（与工作流的封面/视频预览共用同一个竖向三等分区域，切到这两个 Tab 时会临时让出上 2/3 空间，日志区始终保留在底部，方便随时看到 LLM 分析进度）。两个 Tab 都是**单击宫格预览、双击（或右侧「播放」按钮）在系统默认浏览器打开播放**（Tkinter 无法内嵌 YouTube 播放器）。「爆款分析」的 `search.list` 配额较贵（单次 100 配额，每个关键词会各查一次「按播放量」+一次「按最新发布」共 200 配额），搜索结果本地缓存 24 小时，工具栏可选「刷新（重新抓取）」或「使用缓存加载」。

**上传前置**：

1. Google Cloud OAuth 客户端 JSON 放到 `scripts/video_upload/config/`（见 [`scripts/video_upload/README.md`](../scripts/video_upload/README.md)）
2. 已完成第 2 步（含物料生成）
3. 已用 `export_mp4.sh` 将成片导出到子工程 `material/`（上传时按物料目录名匹配 MP4）
4. 首次点击上传会在浏览器完成 OAuth；令牌按账号保存在 `config/token_leo.json` / `token_leo_usa.json`

上传选项：可见性（unlisted / private / public）、标题/描述语言（en / zh）、**leo_usa** 勾选（默认 `leo` 账号）。

## WSL 说明

Reaper 在 Windows 侧运行，GUI 会通过 `cmd.exe` 调用 Windows 版 Reaper。

**YouTube OAuth（WSL）**：首次上传会在 **Windows 浏览器**打开 Google 授权页（非 `xdg-open`）；授权完成后自动回到 GUI。

本地偏好保存在 `gui/user_config.json`（已 gitignore）。
