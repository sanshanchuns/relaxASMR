# Epidemic Sound 雨声音效下载

从 [Epidemic Sound](https://www.epidemicsound.com/) 按 **英文关键词** 搜索音效，每词下载 **Top 15** 预览 MP3，写入 `assets/sound_effect/rain_sound/`（与剪映 / Envato 合并 manifest）。

---

## API（参考 reference.yaml）

```
GET https://www.epidemicsound.com/json/search/sfx/
  ?term=rain heavy
  &page=1
  &sort=relevance
  &segment_types=music-structure@v2
  &segment_types=predicted-popular-15sec
  &segment_types=soundly-sfx
```

必需请求头：`Cookie`、`epidemic-workspace-id`、`x-csrftoken`、`app-version`。

预览音频：`entities.tracks[id].stems.full.lqMp3Url`（`audiocdn.epidemicsound.com/lqmp3/...mp3`）

---

## 前置

- Python 3.8+、`curl`
- Epidemic 订阅账号凭据（见 [reference.yaml](reference.yaml)）
- Cloudflare 拦截时：`pip install -r requirements.txt`（共享 [cloak_browser](../cloak_browser/README.md)）

---

## 凭据

登录 [epidemicsound.com](https://www.epidemicsound.com/) 后，从 DevTools 复制 curl 写入 `reference.yaml`，或：

```bash
export EPIDEMIC_COOKIE='client_session_id=...; sessionid=...; csrftoken=...'
export EPIDEMIC_WORKSPACE_ID='9daa6af6-...'
export EPIDEMIC_CSRF_TOKEN='...'   # 可与 Cookie 中 csrftoken 相同
```

---

## 用法

```bash
cd scripts/epidemic_audio

python3 download.py --list

# 单层 / 全部（默认 mp3，curl + Cloudflare 时自动 CloakBrowser）
python3 download.py --layer 2_rain
./fetch.sh

# 只搜索
python3 download.py --layer 2_rain --dry-run

# 始终用 CloakBrowser
python3 download.py --layer 2_rain --browser --dry-run
```

---

## 配置 · `rain_layers.json`

与 [envato_audio](../envato_audio/rain_layers.json) 同结构的 7 层英文关键词；`output_dir` 默认 `assets/sound_effect/rain_sound`。

manifest 字段 `source=epidemic_sound`，与 `capcut`、`envato_elements` 合并。

---

## 说明

- 下载的是 **lqMp3** 预览（与站内试听一致），非无损 stem。
- Cookie 过期时需更新 `reference.yaml`。
- Profile 默认：`scripts/cloak_browser/.profiles/epidemic/`
