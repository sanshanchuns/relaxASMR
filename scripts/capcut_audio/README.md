# 剪映音效分层下载（雨声库）

从剪映（ulikecam）音效 API 按 7 层结构 + 中文关键词批量下载雨声音效，供 Reaper 工程使用。

## 前置

- Python 3.8+
- 网络可访问 `lv-api-sinfonlinec.ulikecam.com`

## 配置

- 分层关键词：[layers.json](layers.json)
- 声音设计文档：[design/rain_series/rain_sound_design.md](../../design/rain_series/rain_sound_design.md)

修改 `layers.json` 中的 `keywords` 或 `defaults.per_keyword` 即可调整下载范围。

## 用法

```bash
# 列出全部层级
python3 download.py --list

# 仅搜索，不下载
python3 download.py --dry-run --layer 2_rain

# 下载单层
python3 download.py --layer 2_rain

# 下载全部层级（默认每关键词 15 条，含付费）
python3 download.py --all

# 或使用包装脚本
./fetch.sh

# 仅免费素材
python3 download.py --all --free-only

# 自定义每关键词条数
python3 download.py --all --per-keyword 10
```

## 输出结构

```
output/
├── 1_base/
│   ├── 风声/
│   │   └── <id>_<title>.mp3
│   ├── manifest.json
├── 2_rain/
│   └── ...
└── ...
```

## manifest.json 字段

| 字段 | 说明 |
|------|------|
| `layer_id` | 层级 ID |
| `keyword` | 搜索关键词 |
| `id` | 音效 ID |
| `title` | 标题 |
| `duration` | 时长（秒） |
| `paid_type` | free / vip / unknown |
| `url` | 原始下载链接 |
| `local_path` | 相对脚本目录的本地路径 |
| `status` | downloaded / skipped / failed / dry_run |

## API 说明

- 接口：`artist/v1/effect/search`
- 下载链接：`common_attr.download_info.url`
- 付费类型：`common_attr.business_info.json_str` 内 `paid_type`
- 参考原始 curl：[scripts/capcut_script.md](../capcut_script.md)

## 注意

- `output/` 已加入 `.gitignore`，音频不提交仓库
- 已存在文件会跳过（断点续传）
- 跨关键词按 `md5`/`id` 全局去重
