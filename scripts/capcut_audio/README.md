# 剪映音效/音乐分层下载

从剪映（ulikecam）API 按分层结构 + 中文关键词批量下载音效与音乐，供 Reaper 工程使用。当前内置两套配置：

- 雨声库 [rain_layers.json](rain_layers.json) → 输出 `assets/rain_sound/`
- 湖泊库 [lake_layers.json](lake_layers.json) → 输出 `assets/lake_sound/`

## 前置

- Python 3.8+
- 网络可访问 `lv-api-sinfonlinec.ulikecam.com`（音效）与 `lv-pc-api-sinfonlinec.ulikecam.com`（音乐）

## 配置

- 声音设计文档：[design/rain_series/rain_sound_design.md](../../design/rain_series/rain_sound_design.md)、[design/lake_series/lake_sound_design.md](../../design/lake_series/lake_sound_design.md)
- 每个配置文件含 `defaults` 与 `layers` 两部分。

### defaults 字段

| 字段 | 说明 | 默认 |
|------|------|------|
| `per_keyword` | 每个音效关键词下载条数 | 15 |
| `per_collection` | 每个音乐歌单下载条数 | 30 |
| `commercial_only` | 仅下载可商用素材 | false |
| `page_size` | API 分页大小 | 50 |
| `output_dir` | 输出子目录 | `output` |

### layer 类型

- `type: effect`（默认）：用 `keywords` 列表调用音效搜索。
- `type: music`：用 `collections`（`{name, id}` 歌单）调用音乐接口。

## 用法

```bash
# 列出层级（雨声）
python3 download.py --list

# 列出层级（湖泊）
python3 download.py --config lake_layers.json --list

# 雨声：下载单层 / 全部
python3 download.py --layer 2_rain
python3 download.py --all

# 湖泊：仅搜索预览
python3 download.py --config lake_layers.json --dry-run --layer 7_music

# 湖泊：全部（仅商用，配置已默认开启）
python3 download.py --config lake_layers.json --all

# 不限商用许可，下载全部
python3 download.py --config lake_layers.json --all --all-licenses

# 自定义每组条数
python3 download.py --config lake_layers.json --all --target 10
```

`./fetch.sh` 为雨声库的薄包装（`download.py --all`）。

## 商用过滤

`commercial_only=true` 时：

- 音效：`business_info` 中 `paid_type==free` 或导出策略含 `free`（可免费商用）。
- 音乐：`is_commerce==true`（可商用）。注意部分音乐 `paid_type==subscribe`，需剪映 Pro 订阅方可商用导出，manifest 中已记录 `paid_type` 供甄别。

## 输出结构

```
assets/lake_sound/
├── 1_water/
│   ├── 湖水/<id>_<title>.mp3
│   └── manifest.json
├── 7_music/
│   ├── 舒缓/<id>_<title>.m4a
│   └── manifest.json
└── ...
```

音效存为 `.mp3`，音乐（preview_url）存为 `.m4a`。

## manifest.json 字段

| 字段 | 说明 |
|------|------|
| `layer_id` / `layer_name` / `layer_type` | 层级信息（effect / music） |
| `group` | 音效为关键词，音乐为歌单名 |
| `id` / `title` | 素材 ID 与标题 |
| `author` | 音乐作者（仅 music） |
| `duration` | 时长（秒） |
| `paid_type` | free / vip / subscribe / unknown |
| `is_commerce` | 是否可商用（仅 music） |
| `url` | 原始下载链接 |
| `local_path` | 相对脚本目录的本地路径 |
| `status` | downloaded / skipped / failed / dry_run |

## API 说明

- 音效搜索：`artist/v1/effect/search`，下载链接 `common_attr.download_info.url`
- 音乐歌单：`lv/v1/get_collection_songs`，下载链接 `song.preview_url`，商用标记 `song.is_commerce`
- 参考原始 curl：[scripts/capcut_script.md](../capcut_script.md)

## 素材整理（curate）

按 [curate_rules.json](curate_rules.json) 与设计文档筛选，删除综艺/UI/短促提示音等不相关素材：

```bash
python3 curate.py --all --dry-run   # 预览
python3 curate.py --all             # 删除并更新 manifest
python3 curate.py --rain            # 仅雨声库
python3 curate.py --lake            # 仅湖泊库
```

## 注意

- `assets/rain_sound/`、`assets/lake_sound/` 音频由全局 `*.mp3`/`*.m4a` 忽略
- 已存在文件会跳过（断点续传）
- 跨关键词/歌单按 `md5`/`id` 全局去重
