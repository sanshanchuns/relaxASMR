# ElevenLabs AI 音效生成

使用 [ElevenLabs Sound Effects API](https://elevenlabs.io/docs/eleven-api/guides/cookbooks/sound-effects) 生成音效，输出到仓库 `assets/api_sound/`。

## 输出格式

每个条目一对文件：

| 文件 | 说明 |
|------|------|
| `api_<id>.wav` | AI 生成音频（PCM 44100Hz 转 WAV） |
| `api_<id>.json` | 描述词 `text` 与生成参数 |

批量生成后另有 `assets/api_sound/index.json` 索引。

## 前置

```bash
pip install -r requirements.txt
source ~/.zshrc   # ELEVENLABS_API_KEY
```

## 用法

### 单条生成

```bash
python3 generate.py "Light rain on calm lake, soft ASMR ambience" \
  --duration 30 --loop

# 指定文件名后缀
python3 generate.py "Gentle wind through reeds" --slug reed_test --duration 20

# 预览
python3 generate.py "test prompt" --dry-run
```

无 `--slug` 时自动编号：`api_001.wav`、`api_002.wav` …

### 批量（prompts.json）

```bash
python3 generate.py --list
python3 generate.py --all
./generate.sh
python3 generate.py --id lake_gentle_lap --id rain_light_lake
```

预设 id 对应文件名，如 `api_lake_gentle_lap.wav`。

## api_xx.json 示例

```json
{
  "text": "Gentle lake waves lapping against a sandy shore...",
  "slug": "lake_gentle_lap",
  "layer": "water",
  "series": "lake",
  "duration_seconds": 30,
  "loop": true,
  "prompt_influence": 0.35,
  "model_id": "eleven_text_to_sound_v2",
  "generated_at": "2026-06-25T08:00:00",
  "source": "elevenlabs"
}
```

## 素材目录总览

见 [assets/README.md](../../assets/README.md)。

| 目录 | 来源 |
|------|------|
| `assets/rain_sound/` | 剪映下载（雨声） |
| `assets/lake_sound/` | 剪映下载（湖泊） |
| `assets/api_sound/` | ElevenLabs 生成 |

## 注意

- 生成按 ElevenLabs 配额计费，批量前建议 `--dry-run`
- 已存在 `api_xx.wav` 会跳过
- `*.wav` 已在 `.gitignore`，`api_xx.json` 可提交仓库
