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

1. **导入 Loop 视频** — 选择 MP4，自动规范化到 baseURL
2. **选择四轨声音库** — CLIP/VLM 推荐 `1_rain` 候选，各轨点选 WAV
3. **新建 Reaper 工程** — GUI 选音 → 内存构建配置 → 直接生成 `.rpp`（不写配置文件）
4. **导出音频与合成视频** — 一键混音、合成 MP4
5. **上传到 YouTube** — 从物料目录读取元数据并上传成片

### 顶部 Tab 结构

| 顶部 Tab | 子 Tab |
|----------|--------|
| **工作流** | —（上面的步骤 1–5） |
| **数据分析** | 我的数据、爆款分析 |
| **素材库** | 视频、rain boom、impact、random、wildlife |
| **系列视频** | —（见下方「系列视频 Tab」） |

### 数据分析 Tab

| 子 Tab | 数据来源 | 功能 |
|-----|----------|------|
| **我的数据** | `YOUTUBE_DATA_API_KEY` + `agy`（LLM） | 展示自有频道（ace.leo.zhu@gmail.com）订阅人数、总视频数；视频按 YouTube 播放列表（系列）分组，每组内按播放量降序排列，宫格展示封面+标题（超长标题省略号），未加入任何播放列表的视频归入「未分类」；可对单个视频发起 LLM「优劣分析」（同时指出优点和不足，给改进建议） |
| **爆款分析** | `YOUTUBE_DATA_API_KEY` + `agy`（LLM） | 关键词默认「leaf rain」，可在输入框自定义（逗号分隔可搜多个），围绕关键词搜索同类高赞/高评论/高观看的爆款视频，按作者分组宫格展示，组内按「日均播放量」（归一化，识别快速增长的黑马）排序展示 Top 10；点击视频预览+可发起 LLM（Gemini，含封面图）分析爆款优点；点击作者查看其订阅人数/注册时间/总观看次数；每个分组标题栏右上角「✕」可删除该分组，删除后自动从预备池里补一个新分组（优先选「总播放量不高但增速很快」的黑马作者） |

两个子 Tab 只负责左侧宫格；预览缩略图、LLM 分析结果、「在浏览器中播放」按钮统一渲染在应用最外层的**右半边**（与工作流的封面/视频预览共用同一个竖向三等分区域，切到这两个 Tab 时会临时让出上 2/3 空间，日志区始终保留在底部，方便随时看到 LLM 分析进度）。两个 Tab 都是**单击宫格预览、双击（或右侧「播放」按钮）在系统默认浏览器打开播放**（Tkinter 无法内嵌 YouTube 播放器）。「爆款分析」的 `search.list` 配额较贵（单次 100 配额，每个关键词会各查一次「按播放量」+一次「按最新发布」共 200 配额），搜索结果本地缓存 24 小时，工具栏可选「刷新（重新抓取）」或「使用缓存加载」。

### 系列视频 Tab

主题固定为「雨 + 打击物（叶片/水面）+ ASMR 感（打击感、水珠飞溅、水气）」。一条流水线走完
**种子图 → 同系列图片 → 每张图一段 720p / 16:9 / 固定镜头 5s loop 视频**（默认 Jimeng 网页；回退 ElevenLabs HTTP → ElevenLabs Web）。

左栏三列（横向可拖动分栏），第二、三列滚动联动，所以「第 N 张系列图」和「它的视频」
永远在同一行：

顶部两行：生图额度 | 生视频额度（左右并排），下方操作区；第二、三列滚动联动：

| 区域 | 内容 |
|------|------|
| 生图额度 | agy 邮箱、japan/usa/main、Weekly / Five Hour 剩余 |
| 生视频额度 | Jimeng 登录态、ElevenLabs HTTP character 已用/总额；点击刷新 |
| 操作区 | 批次、系列图张数、生图；视频模型、生视频；即梦/EL 网页登录 |

| 列 | 内容 | 交互 |
|----|------|------|
| ① 种子图 | 定稿种子图 + 文生图待选候选 | 「选择种子图…」导入；或填想法后「用 prompt 生成」多张候选，双击/「定稿」选一张 |
| ② 系列图 | agy Gemini **图生图**生成的同系列图；下方显示 prompt 得分 | 单击预览；双击为它生成视频；右键可重生/删除 |
| ③ 对应视频 | 每张系列图的 5s loop；下方显示视频 prompt 得分 | 单击在右侧循环播放；双击重新生成 |

右侧复用工作流同款「封面预览 + 视频预览 + 日志」三区：系列图/种子图显示在封面区，
对应视频在视频预览区**循环播放**（与工作流导入 MP4 后相同的 OpenCV loop 逻辑），
提示词分别显示在封面/视频区右侧文案框；下 1/3 仍是日志区。

**提示词最佳实践（强制）**：正文与机器校验规则写在 [`instructions/`](../instructions/)：

| 环节 | 规范文件 | 公式 |
|------|----------|------|
| 文生图 / 图生图 | [`rain_asmr_image_prompt.md`](../instructions/rain_asmr_image_prompt.md) | `时间 + 主体 + 场景 + 风格` |
| 图生视频 | [`rain_asmr_video_prompt.md`](../instructions/rain_asmr_video_prompt.md) | Seedance 6 步：主体→动作→环境→镜头→风格→约束 |

[`scripts/series_video/prompt_rules.py`](../scripts/series_video/prompt_rules.py) 在每次调用模型**之前**解析规范末尾的 JSON 规则并校验；不通过直接拒绝，不会消耗额度。
同一套规则也用来打 **0–100 分**（通过项占比），显示在系列图 / 对应视频宫格下方。拼装逻辑在 [`prompts.py`](../scripts/series_video/prompts.py)。

**模型分工**：

- **出图（种子候选 + 系列图）**：agy Gemini（`gemini-3.1-flash-image`），只负责图
- **出视频**：外部 provider，**回退 Jimeng Web → ElevenLabs HTTP → ElevenLabs Web**

视频 provider 注册表在 [`video_gen.py`](../scripts/series_video/video_gen.py)，工具栏下拉框自动列出可用性：

| provider | 说明 |
|----------|------|
| `jimeng_web` | 即梦画布 Playwright（720p/5s）；见 [`cli/jimeng_web/`](../cli/jimeng_web/) |
| `elevenlabs_http` | Firebase Bearer HTTP（480p/5s）；见 [`cli/elevenlabs_http/`](../cli/elevenlabs_http/) |
| `elevenlabs_web` | ElevenLabs Image&Video 页 Playwright（480p/5s）；见 [`cli/elevenlabs_web/`](../cli/elevenlabs_web/) |
| `seedance` / `ffmpeg` | 仅 `SERIES_VIDEO_EXTRA_PROVIDERS=1` 时注册 |

```bash
PYTHONPATH=cli:. python -m jimeng_web login
PYTHONPATH=cli:. python -m elevenlabs_http login   # HTTP token
PYTHONPATH=cli:. python -m elevenlabs_web login    # 网页 profile（HTTP 失败时）
export ELEVENLABS_VIDEO_API_KEY="…"
export ARK_API_KEY="…"                       # SERIES_VIDEO_EXTRA_PROVIDERS=1 时
```

或写 `scripts/config/series_video.json`（已加进 `.gitignore`）。

**产物目录**（`baseURL/series/<批次时间戳>/`）：`seed.png`（或定稿前只有 `seed_candidates/`）、
`images/NNN.png`、`clips/NNN.mp4`、`batch.json`。`batch.json` 是唯一事实来源。

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
