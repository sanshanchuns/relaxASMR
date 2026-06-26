# Envato Elements 雨声音效下载

从 [Envato Elements](https://elements.envato.com/) 按 **英文关键词** 搜索音效，每词下载 **Top 15** 预览音频，写入 `assets/rain_sound/` 对应分层目录。

对标 [capcut_audio](../capcut_audio/README.md) 的分层结构，关键词对齐 [rain_sound_design.md](../../design/rain_series/rain_sound_design.md)（英文版见 [rain_layers.json](rain_layers.json)）。

---

## 取数方式（参考 envato_API.yaml）

| 方式 | 说明 |
|------|------|
| **HTML 直抓** | `GET https://elements.envato.com/sound-effects/nature-sounds/<keyword>` |
| **data-api** | `GET .../data-api/page/items-neue-page?path=...&clientVersion=...` |

两种方式返回的 HTML 结构相同，脚本从当前页所有 `<source src="...preview.m4a|mp3">` 解析预览 URL，并关联 `title-link` / `author-link`。

关键词路径示例：

- `rain` → `/sound-effects/nature-sounds/rain`
- `rain grass` → `/sound-effects/nature-sounds/rain+grass`
- `light rain` → `/sound-effects/nature-sounds/light+rain`

---

## 前置

- Python 3.8+
- `curl`
- 有效的 Envato Elements 订阅账号 Cookie（见 [envato_API.yaml](envato_API.yaml)）

---

## 凭据

在浏览器登录 [elements.envato.com](https://elements.envato.com/) 后，将 DevTools 里复制的 Cookie 写入 `envato_API.yaml` 第一条 curl 的 `-H "Cookie: ..."`，或设置环境变量：

```bash
export ENVATO_COOKIE='envato_client_id=...; cf_clearance=...; ...'
```

`clientVersion` / `enrollments` 可从 yaml 中 data-api 那条 curl URL 自动读取。

---

## 用法

```bash
cd scripts/envato_audio

# 列出层级与英文关键词
python3 download.py --list

# 离线验证解析（无需 Cookie）
python3 download.py --parse-html rain.html --target 15

# 单层 / 全部（默认 auto：先 HTML，失败再 data-api）
python3 download.py --layer 2_rain
./fetch.sh

# 指定取数方式 / 预览格式
python3 download.py --layer 2_rain --fetch-mode html
python3 download.py --layer 2_rain --fetch-mode api
python3 download.py --layer 2_rain --format mp3

# 只搜索、不下载
python3 download.py --layer 2_rain --dry-run
```

---

## 配置 · `rain_layers.json`

| 字段 | 说明 |
|------|------|
| `search_path_prefix` | 默认 `/sound-effects/nature-sounds` |
| `per_keyword` | 每关键词取前 N 条（默认 15） |

| 层级 | 英文关键词示例 |
|------|----------------|
| `1_base` | wind, light breeze, forest ambience, white noise |
| `2_rain` | drizzle, light rain, rain, heavy rain, storm rain |
| `3_impact` | rain on leaves, rain on roof, rain on window, rain on umbrella |
| `4_water` | water drop, roof drip, creek, flowing water, lake water |
| `5_env` | bamboo rain, forest rain, city rain |
| `6_life` | birds, frog, cricket, cicada, duck |
| `7_accent` | thunder, campfire, wind chime, rowing boat |

---

## 输出结构

```
assets/rain_sound/
├── 2_rain/
│   ├── light_rain/
│   │   ├── D7TWQNL_Rain.m4a
│   │   └── ...
│   └── manifest.json    # 与剪映素材合并，source=envato_elements
└── ...
```

manifest 额外字段：`preview_m4a`, `preview_mp3`, `fetch_via`（html / api）。

---

## 说明

- 下载的是 Elements **预览音频**（m4a 或 mp3），与浏览器试听一致。
- 同一层 manifest 会与已有剪映条目 **合并**，不会覆盖 `source=capcut` 记录。
- Cookie 过期时两种 fetch 都会失败，需更新 `envato_API.yaml`。
