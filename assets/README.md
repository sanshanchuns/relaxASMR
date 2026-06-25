# 素材库（assets）

| 目录 | 内容 | 来源 |
|------|------|------|
| `rain_sound/` | 雨声系列分层音效 | 剪映 API 下载 + curate |
| `lake_sound/` | 湖泊系列分层音效与音乐 | 剪映 API 下载 + curate |
| `rain_video/` | 雨景循环视频 | 实拍 / 后期 |
| `lake_video/` | 湖景循环视频 | 实拍 / 后期 |
| `api_sound/` | AI 生成音效 | ElevenLabs API，`api_xx.wav` + `api_xx.json` |

## api_sound 命名

- 音频：`api_<id>.wav`（如 `api_lake_gentle_lap.wav`）
- 描述：`api_<id>.json`（记录提示词与生成参数）
- 单条无 id 时自动递增：`api_001.wav`、`api_002.wav` …

生成命令见 [scripts/ai_audio/README.md](../scripts/ai_audio/README.md)。
