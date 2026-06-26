# YouTube Top3 竞品抓取

按 **主题系列** 从 YouTube 搜索近 **30 天** 发布、播放量 **≥ 3 万** 的视频，取 **Top 3**，并自动下载每支视频的 **前 300 秒** 到本地供案例分析。

对标 [youtube_rank.md](../youtube_rank.md) 中 ASMR / 自然声赛道的「30 天 3 万+ = 优秀」分级。

---

## 依赖

```bash
pip install -r scripts/youtube_top3/requirements.txt
# 系统还需 ffmpeg（macOS: brew install ffmpeg）
```

---

## 用法

```bash
cd scripts/youtube_top3

# 列出主题系列
./fetch_top3.sh --list

# 抓取单个系列
./fetch_top3.sh --series morning_mist_lake

# 抓取全部系列
./fetch_top3.sh --all

# 只搜索、不下载（调试关键词）
./fetch_top3.sh --series morning_mist_lake --dry-run
```

---

## 配置 · `series.json`

| 字段 | 默认 | 说明 |
|------|------|------|
| `days` | 30 | 仅保留近 N 天 **发布** 的视频 |
| `min_views` | 30000 | 最低播放量 |
| `top_n` | 3 | 取 Top N |
| `clip_seconds` | 300 | 每支下载前 N 秒 |
| `search_limit` | 40 | 每条 query 搜索条数 |
| `queries` | — | 每系列可多条搜索词 |

新增系列：在 `series` 下加一项即可。

---

## 输出

```
output/{series_id}/{YYYYMMDD_HHMMSS}/
├── report.md      # 人类可读摘要
├── manifest.json  # 机器可读（URL、播放、片段路径）
└── clips/
    ├── 01_{videoId}_300s.mp4
    ├── 02_{videoId}_300s.mp4
    └── 03_{videoId}_300s.mp4
```

---

## 说明

- **30 天播放量**：YouTube 公开接口无「近 30 日增量」，本模块用 **发布日在 30 天内** 的视频 **总播放量** 近似（新视频误差小）。
- 下载默认 **720p** 以加快速度；可在 `series.json` 的 `defaults.max_height` 调整。
- `output/` 含 mp4，体积大，已加入 `.gitignore`。

---

## 预设系列

关键词对齐 [lake_typic_scene.md](../../design/lake%20series/lake_typic_scene.md)：每系列以 **场景类型 + 代表湖名** 搜索。

| ID | 主题 |
|----|------|
| `morning_mist_lake` | 晨雾湖泊 · Lake Bled |
| `lakeside_breeze` | 湖边微风 · Lake Windermere |
| `wooden_pier` | 湖畔木码头 · Lake Bohinj |
| `rain_on_lake` | 湖面雨声 · Lake Kawaguchi |
| `evening_lake` | 黄昏湖泊 · Lake Annecy |
| `lake_campfire` | 湖边篝火 · Lake Tahoe |
| `floating_boat` | 小船漂浮 · Lago di Braies |
| `alpine_lake` | 高山冰川湖 · Lake Louise |
| `reed_lake` | 芦苇湖 · Neusiedler See |
| `waterbird_lake` | 天鹅湖 · Lake Hallstatt |
