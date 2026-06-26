# ElevenLabs AI 音效生成

使用 [ElevenLabs Sound Effects API](https://elevenlabs.io/docs/eleven-api/guides/cookbooks/sound-effects) 生成音效，输出到 `assets/api_sound/<category>/`。

**原则**：保存 API PCM 原声；落地 MP3 仅做 ffmpeg 转码（无混响/EQ）。**生成后必须试听**。

## 响度问题说明

ElevenLabs 直接返回的 `mp3_44100_128` 有时峰值仅 **-50～-60 dB**（近乎无声）。  
当前流程：**API 固定 `pcm_44100` → ffmpeg 转 MP3**，并自动检测响度。

| max_volume | 判定 |
|------------|------|
| ≥ -36 dB | OK |
| -48 ～ -36 dB | WARN 偏低，建议试听 |
| < -48 dB | FAIL 近乎无声，需 `--force` 重生成 |

## 输出格式

| 文件 | 说明 |
|------|------|
| `<category>/api_<id>.mp3` | API PCM 原声 → ffmpeg MP3 128kbps |
| `<category>/api_<id>.json` | 提示词、响度、`post_process: format_only` |

分类目录：`bird/`、`rain/`、`water/`、`wind/`、`accent/` …

## 前置

```bash
pip install -r requirements.txt
source ~/.zshrc   # ELEVENLABS_API_KEY
# 需要 ffmpeg、ffplay（试听）
```

## 用法

### 生成

```bash
python3 generate.py --id mvi6918_bird_distant --force --play
python3 generate.py --all
./generate.sh
```

`--play`：生成后自动播放。`--force`：覆盖已存在文件。

### 试听 / 校验（生成后必做）

```bash
python3 audition.py                    # 检查全部 api_sound
python3 audition.py mvi6918_bird_distant --play   # 指定 slug 播放
python3 audition.py --play-only bird/api_mvi6918_bird_distant.mp3
python3 audition.py --update-json      # 响度写回 json
```

## api_xx.json 示例

```json
{
  "api_format": "pcm_44100",
  "file_format": "mp3",
  "post_process": "format_only",
  "loudness": {
    "max_volume_db": -28.5,
    "mean_volume_db": -42.1,
    "verdict": "pass"
  }
}
```

## 注意

- 生成按 ElevenLabs 配额计费
- `assets/api_sound/**/*.mp3` 已在 `.gitignore`，`*.json` 可提交
